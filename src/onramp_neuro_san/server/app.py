"""ONRAMP FastAPI application.

Local-first onboarding workbench. Serves the operational UI and a JSON API.
The Concierge review endpoint drives the real Neuro-SAN network; on any failure
it records the error and the case cannot be approved.
"""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import db, checks as checks_mod, provider, neuro_client
from ..config import (
    AGENT_NAME, FRONTEND_DIR, UPLOADS_DIR, MAX_UPLOAD_BYTES,
    ALLOWED_UPLOAD_EXTENSIONS, ensure_dirs,
)
from . import review
from . import samples


@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    ensure_dirs()
    db.init_db(seed=True)
    # Ensure the served network's llm_config matches the active provider, in
    # case settings were changed while the server was down.
    try:
        provider.write_network_llm_config()
    except OSError:
        pass
    yield


app = FastAPI(title="ONRAMP", version="0.2.0",
              description="Local-first, human-governed client onboarding on neuro-san.",
              lifespan=_lifespan)


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------
class CaseCreate(BaseModel):
    client_name: str
    segment: str = ""
    tcv: str = ""
    opportunity_ref: str = ""
    delivery_owner: str = ""
    stakeholders: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []


class EvidenceCreate(BaseModel):
    kind: str
    label: str = ""
    facts: dict[str, Any] = {}


class Disposition(BaseModel):
    disposition: str  # cleared | failed | hold
    reviewer: str
    rationale: str = ""


class SignoffCreate(BaseModel):
    gate: str
    reviewer: str
    note: str = ""


class SettingsUpdate(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class RoiUpdate(BaseModel):
    hourly_rate_usd: float | None = None
    human_baseline_minutes: float | None = None


# --------------------------------------------------------------------------
# Health & meta
# --------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    cfg = provider.active_config()
    probe = neuro_client.ping()
    return {
        "status": "ok",
        "agent_name": AGENT_NAME,
        "provider": cfg.provider,
        "model": cfg.model,
        "provider_key_configured": cfg.has_key,
        "neuro_san": probe,
    }


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------
@app.get("/api/cases")
def list_cases() -> list[dict[str, Any]]:
    cases = db.list_cases()
    for c in cases:
        c["summary"] = _case_summary(c["id"])
    return cases


@app.post("/api/cases")
def create_case(body: CaseCreate) -> dict[str, Any]:
    return db.create_case(body.model_dump())


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    case["evidence"] = db.list_evidence(case_id)
    case["checks"] = db.list_checks(case_id)
    case["signoffs"] = db.list_signoffs(case_id)
    case["agent_runs"] = db.list_agent_runs(case_id)
    case["summary"] = _case_summary(case_id)
    return case


def _case_summary(case_id: str) -> dict[str, Any]:
    checks = db.list_checks(case_id)
    summary = checks_mod.summarise(checks)
    latest = db.latest_successful_run(case_id)
    summary["has_successful_run"] = latest is not None
    summary["approvable"] = summary["gate_clear"] and latest is not None
    return summary


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/evidence")
def add_evidence(case_id: str, body: EvidenceCreate) -> dict[str, Any]:
    if db.get_case(case_id) is None:
        raise HTTPException(404, "case not found")
    return db.add_evidence(case_id, body.model_dump(),
                           actor=_owner(case_id))


@app.post("/api/cases/{case_id}/uploads")
async def upload_evidence(case_id: str, kind: str = Form(...),
                          label: str = Form(""),
                          file: UploadFile = File(...)) -> dict[str, Any]:
    if db.get_case(case_id) is None:
        raise HTTPException(404, "case not found")
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(400, f"unsupported file type '{ext}'. "
                                 f"Allowed: {', '.join(ALLOWED_UPLOAD_EXTENSIONS)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "file exceeds 15 MB limit")
    sha = hashlib.sha256(data).hexdigest()
    ensure_dirs()
    stored = UPLOADS_DIR / f"{case_id}_{sha[:12]}{ext}"
    stored.write_bytes(data)
    return db.add_evidence(case_id, {
        "kind": kind, "label": label or (file.filename or ""),
        "facts": {}, "filename": file.filename,
        "sha256": sha, "size_bytes": len(data),
    }, actor=_owner(case_id))


@app.get("/api/evidence/{evidence_id}/download")
def download_evidence(evidence_id: str) -> FileResponse:
    ev = db.get_evidence(evidence_id)
    if ev is None or not ev.get("sha256"):
        raise HTTPException(404, "no stored file for this evidence")
    ext = "." + (ev.get("filename") or "").rsplit(".", 1)[-1].lower() if "." in (ev.get("filename") or "") else ""
    stored = UPLOADS_DIR / f"{ev['case_id']}_{ev['sha256'][:12]}{ext}"
    if not stored.exists():
        raise HTTPException(404, "stored file missing")
    return FileResponse(stored, filename=ev.get("filename") or stored.name)


@app.delete("/api/evidence/{evidence_id}")
def delete_evidence(evidence_id: str) -> dict[str, Any]:
    ev = db.get_evidence(evidence_id)
    if ev is None:
        raise HTTPException(404, "evidence not found")
    case_id = ev["case_id"]
    deleted = db.delete_evidence(evidence_id, actor=_owner(case_id))
    _unlink_stored_file(deleted, case_id)
    return {"status": "deleted", "evidence_id": evidence_id,
            "summary": _case_summary(case_id)}


@app.delete("/api/evidence/{evidence_id}/file")
def remove_evidence_file(evidence_id: str) -> dict[str, Any]:
    """Remove only the attached file, keeping the document record."""
    ev = db.get_evidence(evidence_id)
    if ev is None:
        raise HTTPException(404, "evidence not found")
    if not ev.get("sha256"):
        raise HTTPException(400, "this record has no attached file to remove")
    case_id = ev["case_id"]
    removed = db.remove_file(evidence_id, actor=_owner(case_id))
    _unlink_stored_file(removed, case_id)
    return {"status": "file_removed", "evidence_id": evidence_id,
            "summary": _case_summary(case_id)}


def _unlink_stored_file(row: dict[str, Any] | None, case_id: str) -> None:
    """Best-effort delete of the on-disk uploaded file for an evidence row."""
    if not row or not row.get("sha256"):
        return
    fn = row.get("filename") or ""
    ext = "." + fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
    stored = UPLOADS_DIR / f"{case_id}_{row['sha256'][:12]}{ext}"
    try:
        if stored.exists():
            stored.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# Deterministic checks
# --------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/checks")
def run_checks(case_id: str) -> dict[str, Any]:
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    evidence = db.list_evidence(case_id)
    results = checks_mod.run_checks(evidence)
    db.replace_checks(case_id, results, actor=_owner(case_id))
    return {"checks": db.list_checks(case_id), "summary": _case_summary(case_id)}


@app.post("/api/checks/{check_id}/disposition")
def disposition(check_id: str, body: Disposition) -> dict[str, Any]:
    if body.disposition not in ("cleared", "failed", "hold"):
        raise HTTPException(400, "disposition must be cleared|failed|hold")
    updated = db.disposition_check(check_id, body.disposition, body.reviewer,
                                   body.rationale)
    if updated is None:
        raise HTTPException(404, "check not found")
    return {"check": updated, "summary": _case_summary(updated["case_id"])}


# --------------------------------------------------------------------------
# Concierge review - REAL Neuro-SAN network call (no dummy fallback)
# --------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/review")
def concierge_review(case_id: str) -> JSONResponse:
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    evidence = db.list_evidence(case_id)
    prompt = review.build_prompt(case, evidence)
    sly_data = review.build_sly_data(case, evidence)
    cfg = provider.active_config()

    try:
        result = neuro_client.run_network(prompt, sly_data=sly_data)
    except neuro_client.NeuroSanError as exc:
        run = db.add_agent_run(case_id, {
            "agent_name": AGENT_NAME, "provider": cfg.provider, "model": cfg.model,
            "status": "error", "prompt": prompt, "answer": "",
            "trace": [], "error": str(exc),
        })
        return JSONResponse(status_code=502, content={
            "status": "error",
            "error": str(exc),
            "run": run,
            "summary": _case_summary(case_id),
        })

    run = db.add_agent_run(case_id, {
        "agent_name": AGENT_NAME, "provider": result.provider, "model": result.model,
        "status": "success", "prompt": prompt, "answer": result.answer,
        "trace": result.trace, "error": None, "duration_ms": result.duration_ms,
    })
    return JSONResponse(content={
        "status": "success",
        "answer": result.answer,
        "structure": result.structure,
        "run": run,
        "summary": _case_summary(case_id),
        "roi_run": db.roi_for_run(result.duration_ms),
        "roi_summary": db.roi_summary(),
    })


# --------------------------------------------------------------------------
# Lifecycle sign-offs
# --------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/signoffs")
def add_signoff(case_id: str, body: SignoffCreate) -> dict[str, Any]:
    if db.get_case(case_id) is None:
        raise HTTPException(404, "case not found")
    return db.add_signoff(case_id, body.gate, body.reviewer, body.note)


# --------------------------------------------------------------------------
# Kickoff approval gate (server-side enforcement)
# --------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/approve-kickoff")
def approve_kickoff(case_id: str) -> dict[str, Any]:
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(404, "case not found")

    # Idempotent: if already approved, just make sure the stage reflects it
    # (reconciles any legacy record left at stage 7 by an earlier version).
    if case.get("status") == "kickoff_approved":
        if case.get("stage") != 8:
            db.update_case_stage(case_id, 8, actor=_owner(case_id))
        return {"status": "approved", "summary": _case_summary(case_id)}

    summary = _case_summary(case_id)
    reasons: list[str] = []
    if summary["open_blocks"]:
        reasons.append(f"{summary['open_blocks']} BLOCK check(s) unresolved")
    if summary["open_reviews"]:
        reasons.append(f"{summary['open_reviews']} REVIEW check(s) without human clearance")
    if summary["failed"]:
        reasons.append(f"{summary['failed']} check(s) failed by a reviewer")
    if not summary["has_successful_run"]:
        reasons.append("no successful Neuro-SAN Concierge run recorded")
    if reasons:
        raise HTTPException(409, {"message": "kickoff not approvable", "reasons": reasons,
                                  "summary": summary})
    # Approving the kickoff gate advances the case into the final stage
    # (8 = Hypercare to first value). Stage 7 (Client kickoff) is now passed.
    db.update_case_stage(case_id, 8, actor=_owner(case_id))
    db.set_case_status(case_id, "kickoff_approved", actor=_owner(case_id))
    return {"status": "approved", "summary": _case_summary(case_id)}


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
@app.get("/api/cases/{case_id}/audit")
def audit(case_id: str) -> list[dict[str, Any]]:
    return db.list_audit(case_id)


# --------------------------------------------------------------------------
# Settings / API keys
# --------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    cfg = provider.active_config()
    return {
        "active": {
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "has_key": cfg.has_key,
            "masked_key": cfg.masked_key,
        },
        "providers": provider.provider_options(),
        "key_status": provider.key_status(),
        "neuro_san": neuro_client.ping(),
    }


@app.post("/api/settings")
def update_settings(body: SettingsUpdate) -> dict[str, Any]:
    try:
        provider.save_settings(body.provider, body.model, body.api_key, body.base_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return get_settings()


@app.post("/api/settings/test")
def test_connection() -> dict[str, Any]:
    """Make a real minimal LLM call with the active provider/model."""
    return provider.test_connection()


@app.get("/api/settings/credits")
def credits() -> dict[str, Any]:
    """Return credit/usage info where the provider exposes it."""
    return provider.credits()


# --------------------------------------------------------------------------
# ROI (illustrative savings based on your assumptions)
# --------------------------------------------------------------------------
@app.get("/api/roi")
def get_roi() -> dict[str, Any]:
    return {"settings": db.get_roi_settings(), "summary": db.roi_summary()}


@app.post("/api/roi")
def update_roi(body: RoiUpdate) -> dict[str, Any]:
    if body.hourly_rate_usd is not None and body.hourly_rate_usd < 0:
        raise HTTPException(400, "hourly_rate_usd must be >= 0")
    if body.human_baseline_minutes is not None and body.human_baseline_minutes < 0:
        raise HTTPException(400, "human_baseline_minutes must be >= 0")
    db.set_roi_settings(body.hourly_rate_usd, body.human_baseline_minutes)
    return {"settings": db.get_roi_settings(), "summary": db.roi_summary()}


@app.get("/api/roi/summary")
def roi_summary() -> dict[str, Any]:
    return db.roi_summary()


# --------------------------------------------------------------------------
# Sample onboarding files (for first-time users)
# --------------------------------------------------------------------------
@app.get("/api/samples")
def list_samples() -> list[dict[str, str]]:
    return samples.list_samples()


@app.get("/api/samples/{kind}/download")
def download_sample(kind: str) -> PlainTextResponse:
    sample = samples.get_sample(kind)
    if sample is None:
        raise HTTPException(404, "no sample for this kind")
    return PlainTextResponse(
        sample["body"],
        headers={"Content-Disposition": f'attachment; filename="{sample["filename"]}"'},
    )


def _owner(case_id: str) -> str:
    case = db.get_case(case_id)
    return (case or {}).get("delivery_owner") or "system"


# --------------------------------------------------------------------------
# Frontend (mounted last so API routes take precedence)
# --------------------------------------------------------------------------
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

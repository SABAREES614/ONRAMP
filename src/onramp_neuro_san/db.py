"""SQLite persistence for ONRAMP.

All local, unencrypted, single-file storage (``data/onramp.db``) as befits a
local hackathon build. Tables:

* cases          - one onboarding case per closed-won deal
* evidence       - structured evidence records / uploaded documents (SHA-256)
* checks         - deterministic evidence-check results (PASS/REVIEW/BLOCK)
* signoffs       - named lifecycle sign-offs / attestations
* agent_runs     - captured real Neuro-SAN runs (result + raw trace + status)
* audit          - append-only audit history of every action

The deterministic checks and gate logic live in ``checks.py`` and the API
layer; this module is pure storage.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id            TEXT PRIMARY KEY,
    client_name   TEXT NOT NULL,
    segment       TEXT,
    tcv           TEXT,
    opportunity_ref TEXT,
    delivery_owner  TEXT,
    stakeholders  TEXT,          -- JSON
    commitments   TEXT,          -- JSON
    stage         INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'open',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,   -- e.g. msa, sow, order_form, po, dpa
    label       TEXT,
    facts       TEXT,            -- JSON of structured facts
    filename    TEXT,
    sha256      TEXT,
    size_bytes  INTEGER,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS checks (
    id           TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL,
    code         TEXT NOT NULL,      -- machine code of the check
    title        TEXT NOT NULL,
    result       TEXT NOT NULL,      -- PASS | REVIEW | BLOCK
    detail       TEXT,
    disposition  TEXT,               -- cleared | failed | hold | NULL
    reviewer     TEXT,
    rationale    TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS signoffs (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    gate        TEXT NOT NULL,       -- handoff, compliance, counsel, finance, mobilisation, kickoff, first_value
    reviewer    TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    agent_name  TEXT NOT NULL,
    provider    TEXT,
    model       TEXT,
    status      TEXT NOT NULL,       -- success | error
    prompt      TEXT,
    answer      TEXT,
    trace       TEXT,                -- JSON array of chat messages (raw)
    error       TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS audit (
    id          TEXT PRIMARY KEY,
    case_id     TEXT,
    actor       TEXT,
    action      TEXT NOT NULL,
    detail      TEXT,                -- JSON
    created_at  TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    """Create tables and optionally seed fictional starter cases."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        if seed:
            existing = conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"]
            if existing == 0:
                _seed(conn)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for json_field in ("stakeholders", "commitments", "facts", "detail", "trace"):
        if json_field in out and isinstance(out[json_field], str) and out[json_field]:
            try:
                out[json_field] = json.loads(out[json_field])
            except (json.JSONDecodeError, TypeError):
                pass
    return out


# --- Audit -----------------------------------------------------------------

def record_audit(conn: sqlite3.Connection, *, case_id: str | None, actor: str,
                 action: str, detail: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO audit (id, case_id, actor, action, detail, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (new_id("aud_"), case_id, actor, action,
         json.dumps(detail or {}), now_iso()),
    )


def list_audit(case_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit WHERE case_id = ? ORDER BY created_at DESC, id DESC",
            (case_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Cases -----------------------------------------------------------------

def create_case(data: dict[str, Any]) -> dict[str, Any]:
    cid = new_id("ONB-")
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT INTO cases (id, client_name, segment, tcv, opportunity_ref, "
            "delivery_owner, stakeholders, commitments, stage, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                data.get("client_name", "Unnamed client"),
                data.get("segment", ""),
                data.get("tcv", ""),
                data.get("opportunity_ref", ""),
                data.get("delivery_owner", ""),
                json.dumps(data.get("stakeholders", [])),
                json.dumps(data.get("commitments", [])),
                1,
                "open",
                ts,
                ts,
            ),
        )
        record_audit(conn, case_id=cid, actor=data.get("delivery_owner", "system"),
                     action="case_created",
                     detail={"client_name": data.get("client_name")})
    return get_case(cid)


def get_case(case_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return _row_to_dict(row)


def list_cases() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def update_case_stage(case_id: str, stage: int, actor: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE cases SET stage = ?, updated_at = ? WHERE id = ?",
                     (stage, now_iso(), case_id))
        record_audit(conn, case_id=case_id, actor=actor,
                     action="stage_advanced", detail={"stage": stage})


def set_case_status(case_id: str, status: str, actor: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE cases SET status = ?, updated_at = ? WHERE id = ?",
                     (status, now_iso(), case_id))
        record_audit(conn, case_id=case_id, actor=actor,
                     action="status_changed", detail={"status": status})


# --- Evidence --------------------------------------------------------------

def add_evidence(case_id: str, data: dict[str, Any], actor: str) -> dict[str, Any]:
    eid = new_id("ev_")
    with connect() as conn:
        conn.execute(
            "INSERT INTO evidence (id, case_id, kind, label, facts, filename, "
            "sha256, size_bytes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                eid, case_id, data.get("kind", "other"), data.get("label", ""),
                json.dumps(data.get("facts", {})), data.get("filename"),
                data.get("sha256"), data.get("size_bytes"), now_iso(),
            ),
        )
        # Any evidence change invalidates downstream checks/sign-offs.
        _invalidate_downstream(conn, case_id, actor, reason="evidence_changed")
        record_audit(conn, case_id=case_id, actor=actor, action="evidence_added",
                     detail={"kind": data.get("kind"), "sha256": data.get("sha256")})
    return get_evidence(eid)


def get_evidence(evidence_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
    return _row_to_dict(row)


def list_evidence(case_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE case_id = ? ORDER BY created_at", (case_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Checks ----------------------------------------------------------------

def replace_checks(case_id: str, results: list[dict[str, Any]], actor: str) -> None:
    """Replace all deterministic checks for a case with a fresh run."""
    with connect() as conn:
        conn.execute("DELETE FROM checks WHERE case_id = ?", (case_id,))
        for r in results:
            conn.execute(
                "INSERT INTO checks (id, case_id, code, title, result, detail, "
                "disposition, reviewer, rationale, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id("chk_"), case_id, r["code"], r["title"], r["result"],
                 r.get("detail", ""), None, None, None, now_iso()),
            )
        record_audit(conn, case_id=case_id, actor=actor, action="checks_run",
                     detail={"count": len(results)})


def list_checks(case_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM checks WHERE case_id = ? ORDER BY created_at, id", (case_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def disposition_check(check_id: str, disposition: str, reviewer: str,
                      rationale: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE checks SET disposition = ?, reviewer = ?, rationale = ? WHERE id = ?",
            (disposition, reviewer, rationale, check_id),
        )
        record_audit(conn, case_id=row["case_id"], actor=reviewer,
                     action="check_dispositioned",
                     detail={"check": row["code"], "disposition": disposition,
                             "rationale": rationale})
        updated = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
    return _row_to_dict(updated)


# --- Sign-offs -------------------------------------------------------------

def add_signoff(case_id: str, gate: str, reviewer: str, note: str) -> dict[str, Any]:
    sid = new_id("so_")
    with connect() as conn:
        conn.execute(
            "INSERT INTO signoffs (id, case_id, gate, reviewer, note, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (sid, case_id, gate, reviewer, note, now_iso()),
        )
        record_audit(conn, case_id=case_id, actor=reviewer, action="signoff_recorded",
                     detail={"gate": gate, "note": note})
        row = conn.execute("SELECT * FROM signoffs WHERE id = ?", (sid,)).fetchone()
    return _row_to_dict(row)


def list_signoffs(case_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM signoffs WHERE case_id = ? ORDER BY created_at", (case_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Agent runs ------------------------------------------------------------

def add_agent_run(case_id: str, data: dict[str, Any]) -> dict[str, Any]:
    rid = new_id("run_")
    with connect() as conn:
        conn.execute(
            "INSERT INTO agent_runs (id, case_id, agent_name, provider, model, status, "
            "prompt, answer, trace, error, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid, case_id, data.get("agent_name", ""), data.get("provider", ""),
                data.get("model", ""), data.get("status", "error"),
                data.get("prompt", ""), data.get("answer", ""),
                json.dumps(data.get("trace", [])), data.get("error"), now_iso(),
            ),
        )
        record_audit(conn, case_id=case_id, actor="onboarding_concierge",
                     action="agent_run", detail={"status": data.get("status"),
                                                  "model": data.get("model")})
        row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (rid,)).fetchone()
    return _row_to_dict(row)


def list_agent_runs(case_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def latest_successful_run(case_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM agent_runs WHERE case_id = ? AND status = 'success' "
            "ORDER BY created_at DESC LIMIT 1", (case_id,)
        ).fetchone()
    return _row_to_dict(row)


def _invalidate_downstream(conn: sqlite3.Connection, case_id: str, actor: str,
                           reason: str) -> None:
    """Evidence edits invalidate prior checks, agent runs and sign-offs."""
    conn.execute("DELETE FROM checks WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM agent_runs WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM signoffs WHERE case_id = ?", (case_id,))
    record_audit(conn, case_id=case_id, actor=actor,
                 action="downstream_invalidated", detail={"reason": reason})


# --- Seed data (fictional) -------------------------------------------------

def _seed(conn: sqlite3.Connection) -> None:
    """Insert fictional starter clients from the README demo script."""
    ts = now_iso()
    seeds = [
        {
            "id": "ONB-NORTHWIND01",
            "client_name": "Northwind Logistics",
            "segment": "Mid-market · SaaS",
            "tcv": "$1.2m",
            "opportunity_ref": "OPP-48211",
            "delivery_owner": "A. Patel",
            "stakeholders": [{"role": "Delivery lead", "name": "A. Patel"},
                             {"role": "Account owner", "name": "J. Reyes"}],
            "commitments": [{"item": "Go-live within 8 weeks"},
                            {"item": "2 products, 12-month term"}],
            "evidence": [
                {"kind": "msa", "label": "Executed MSA",
                 "facts": {"liability_cap_multiple": 1.0, "governing_law": "England & Wales"}},
                {"kind": "sow", "label": "SOW-01",
                 "facts": {"milestones": ["M1", "M2", "M3", "M4"]}},
                {"kind": "order_form", "label": "Order form", "facts": {"products": 2}},
                {"kind": "po", "label": "Purchase order",
                 "facts": {"po_number": "PO-7781", "po_matches_sow": True}},
                {"kind": "dpa", "label": "Data Processing Agreement",
                 "facts": {"signed": True, "residency": "UK"}},
            ],
        },
        {
            "id": "ONB-ORION01",
            "client_name": "Orion Retail Group",
            "segment": "Enterprise · Retail",
            "tcv": "$4.1m",
            "opportunity_ref": "OPP-50019",
            "delivery_owner": "M. Okafor",
            "stakeholders": [{"role": "Delivery lead", "name": "M. Okafor"},
                             {"role": "Deal counsel", "name": "S. Bright"}],
            "commitments": [{"item": "Dedicated team from day one (not in SOW)"}],
            "evidence": [
                {"kind": "msa", "label": "Executed MSA",
                 "facts": {"liability_cap_multiple": 3.0,
                           "data_breach_indemnity": "uncapped",
                           "governing_law": "England & Wales"}},
                {"kind": "sow", "label": "SOW-01", "facts": {"milestones": ["M1", "M2"]}},
                {"kind": "order_form", "label": "Order form", "facts": {"products": 5}},
                {"kind": "po", "label": "Purchase order",
                 "facts": {"po_number": "PO-9004", "po_matches_sow": False}},
                {"kind": "dpa", "label": "Data Processing Agreement",
                 "facts": {"signed": True, "residency": "EU"}},
            ],
        },
        {
            "id": "ONB-HELIX01",
            "client_name": "Helix Bank plc",
            "segment": "Enterprise · FS (regulated)",
            "tcv": "$6.8m",
            "opportunity_ref": "OPP-51120",
            "delivery_owner": "R. Hughes",
            "stakeholders": [{"role": "Delivery lead", "name": "R. Hughes"},
                             {"role": "Compliance officer", "name": "D. Mensah"}],
            "commitments": [{"item": "FCA-regulated; EU data residency"}],
            "evidence": [
                {"kind": "msa", "label": "Executed MSA",
                 "facts": {"liability_cap_multiple": 1.0, "governing_law": "England & Wales"}},
                {"kind": "sow", "label": "SOW-01", "facts": {"milestones": ["M1", "M2", "M3"]}},
                {"kind": "order_form", "label": "Order form", "facts": {"products": 3}},
                {"kind": "po", "label": "Purchase order",
                 "facts": {"po_number": "PO-6610", "po_matches_sow": True}},
                # DPA deliberately missing -> stays blocked until added.
            ],
        },
    ]
    for s in seeds:
        conn.execute(
            "INSERT INTO cases (id, client_name, segment, tcv, opportunity_ref, "
            "delivery_owner, stakeholders, commitments, stage, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (s["id"], s["client_name"], s["segment"], s["tcv"], s["opportunity_ref"],
             s["delivery_owner"], json.dumps(s["stakeholders"]),
             json.dumps(s["commitments"]), 2, "open", ts, ts),
        )
        for ev in s["evidence"]:
            conn.execute(
                "INSERT INTO evidence (id, case_id, kind, label, facts, filename, "
                "sha256, size_bytes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id("ev_"), s["id"], ev["kind"], ev["label"],
                 json.dumps(ev["facts"]), None, None, None, ts),
            )
        record_audit(conn, case_id=s["id"], actor="system", action="case_seeded",
                     detail={"client_name": s["client_name"]})

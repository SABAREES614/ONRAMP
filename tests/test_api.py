"""API-level tests using FastAPI's TestClient against a temporary DB.

These exercise the real endpoints end to end. The Concierge review test
asserts the *no-dummy-call* contract: with no neuro-san server / no key, the
call fails, the error is recorded, and the case is not approvable.
"""

import importlib
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setenv("ONRAMP_DB", str(tmp / "test.db"))
    monkeypatch.setenv("ONRAMP_ENV_FILE", str(tmp / ".env"))
    # Ensure no provider key is set so review fails deterministically.
    for var in ("OPENAI_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ONRAMP_PROVIDER", "huggingface")

    # Reimport config/db so the new DB path is picked up.
    import onramp_neuro_san.config as config
    importlib.reload(config)
    import onramp_neuro_san.db as db
    importlib.reload(db)
    import onramp_neuro_san.provider as provider
    importlib.reload(provider)
    import onramp_neuro_san.neuro_client as nc
    importlib.reload(nc)
    import onramp_neuro_san.server.review as review
    importlib.reload(review)
    import onramp_neuro_san.server.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["agent_name"] == "onramp/onramp_onboarding"


def test_seeded_cases_present(client):
    r = client.get("/api/cases")
    assert r.status_code == 200
    names = {c["client_name"] for c in r.json()}
    assert {"Northwind Logistics", "Orion Retail Group", "Helix Bank plc"} <= names


def test_checks_gate_for_northwind_and_helix(client):
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]
    helix = cases["Helix Bank plc"]["id"]

    nw_summary = client.post(f"/api/cases/{nw}/checks").json()["summary"]
    assert nw_summary["gate_clear"] is True

    helix_summary = client.post(f"/api/cases/{helix}/checks").json()["summary"]
    assert helix_summary["open_blocks"] >= 1
    assert helix_summary["gate_clear"] is False


def test_review_without_key_records_error_and_blocks(client):
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]
    client.post(f"/api/cases/{nw}/checks")

    r = client.post(f"/api/cases/{nw}/review")
    assert r.status_code == 502
    body = r.json()
    assert body["status"] == "error"
    assert body["run"]["status"] == "error"
    # Even with clean checks, no successful run => not approvable.
    assert body["summary"]["approvable"] is False

    # And approve-kickoff must be refused.
    ar = client.post(f"/api/cases/{nw}/approve-kickoff")
    assert ar.status_code == 409


def test_approve_kickoff_advances_to_stage_8(client):
    import onramp_neuro_san.db as db
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]  # clean checks, gate clears
    client.post(f"/api/cases/{nw}/checks")
    # Inject a successful Neuro-SAN run so the gate is satisfiable in a test
    # (no live server/key available here).
    db.add_agent_run(nw, {"agent_name": "onramp/onramp_onboarding",
                          "provider": "test", "model": "test", "status": "success",
                          "prompt": "p", "answer": "ok", "trace": [{"text": "ok"}],
                          "error": None})
    summary = client.get(f"/api/cases/{nw}").json()["summary"]
    assert summary["approvable"] is True

    r = client.post(f"/api/cases/{nw}/approve-kickoff")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    case = client.get(f"/api/cases/{nw}").json()
    assert case["stage"] == 8
    assert case["status"] == "kickoff_approved"


def test_evidence_change_invalidates_checks(client):
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]
    client.post(f"/api/cases/{nw}/checks")
    # Add evidence -> downstream checks should be cleared.
    client.post(f"/api/cases/{nw}/evidence",
                json={"kind": "msa", "facts": {"liability_cap_multiple": 1.0}})
    case = client.get(f"/api/cases/{nw}").json()
    assert case["checks"] == []


def test_delete_evidence_removes_and_invalidates(client):
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]
    before = client.get(f"/api/cases/{nw}").json()["evidence"]
    assert len(before) >= 1
    target = before[0]["id"]
    client.post(f"/api/cases/{nw}/checks")  # create checks to be invalidated

    r = client.delete(f"/api/evidence/{target}")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

    after = client.get(f"/api/cases/{nw}").json()
    assert all(e["id"] != target for e in after["evidence"])
    assert len(after["evidence"]) == len(before) - 1
    # Deleting evidence invalidates downstream checks.
    assert after["checks"] == []

    # Deleting a non-existent id 404s.
    assert client.delete("/api/evidence/ev_nonexistent").status_code == 404


def test_remove_file_keeps_record(client):
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]
    # Upload a file for a new kind so we have an evidence record with a sha256.
    files = {"file": ("test.txt", b"hello sample", "text/plain")}
    up = client.post(f"/api/cases/{nw}/uploads", data={"kind": "msa"}, files=files)
    assert up.status_code == 200
    ev_id = up.json()["id"]
    assert up.json()["sha256"]

    # Remove just the file.
    r = client.delete(f"/api/evidence/{ev_id}/file")
    assert r.status_code == 200
    assert r.json()["status"] == "file_removed"

    # The record still exists, but without a file/hash.
    ev = [e for e in client.get(f"/api/cases/{nw}").json()["evidence"] if e["id"] == ev_id]
    assert len(ev) == 1
    assert not ev[0].get("sha256")

    # Removing a file when none is attached -> 400.
    assert client.delete(f"/api/evidence/{ev_id}/file").status_code == 400


def test_settings_masks_key(client, monkeypatch):
    r = client.post("/api/settings", json={
        "provider": "nvidia", "model": "meta/llama-3.3-70b-instruct",
        "api_key": "nvapi-secret-1234567890"})
    assert r.status_code == 200
    body = r.json()
    assert body["active"]["provider"] == "nvidia"
    assert body["active"]["has_key"] is True
    # The raw key must never be returned.
    assert "nvapi-secret-1234567890" not in r.text
    assert "•" in body["active"]["masked_key"]

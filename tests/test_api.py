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


def test_evidence_change_invalidates_checks(client):
    cases = {c["client_name"]: c for c in client.get("/api/cases").json()}
    nw = cases["Northwind Logistics"]["id"]
    client.post(f"/api/cases/{nw}/checks")
    # Add evidence -> downstream checks should be cleared.
    client.post(f"/api/cases/{nw}/evidence",
                json={"kind": "msa", "facts": {"liability_cap_multiple": 1.0}})
    case = client.get(f"/api/cases/{nw}").json()
    assert case["checks"] == []


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

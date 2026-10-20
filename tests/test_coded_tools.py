"""Tests for the deterministic coded tools."""

import pytest

from onramp.clause_playbook import ClausePlaybook
from onramp.checklist_tracker import ChecklistTracker
from onramp.compliance_screen import ComplianceScreen
from onramp.po_reconciler import PoReconciler


@pytest.mark.asyncio
async def test_clause_playbook_within_standard():
    out = await ClausePlaybook().async_invoke(
        {"liability_cap_multiple": 1.0}, {"contract_value": 1_200_000})
    assert out["classification"] == "within_standard"
    # Exposure returned only as a band, not the exact figure.
    assert out["exposure_band"] in ("$1m-$5m", "<$1m")
    assert "1200000" not in str(out)


@pytest.mark.asyncio
async def test_clause_playbook_beyond_fallback():
    out = await ClausePlaybook().async_invoke(
        {"liability_cap_multiple": 3.0}, {"contract_value": 4_100_000})
    assert out["classification"] == "beyond_fallback"


@pytest.mark.asyncio
async def test_checklist_tracker_missing():
    out = await ChecklistTracker().async_invoke(
        {"present_kinds": ["msa", "sow", "order_form", "po"]}, {})
    assert out["complete"] is False
    assert "Data Processing Agreement" in out["missing"]


@pytest.mark.asyncio
async def test_compliance_screen_returns_score_not_identity():
    sly = {"screening_records": {"entity": {"legal_name": "Secret Co", "passport": "X123"}}}
    out = await ComplianceScreen().async_invoke({"subject_ref": "entity"}, sly)
    assert "match_score" in out
    assert 0.0 <= out["match_score"] <= 1.0
    # Identity must not be echoed.
    assert "Secret Co" not in str(out)
    assert "X123" not in str(out)


@pytest.mark.asyncio
async def test_po_reconciler_mismatch_reviews():
    out = await PoReconciler().async_invoke(
        {"po_number": "PO-9", "po_matches_sow": False}, {})
    assert out["status"] == "review"

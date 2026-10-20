"""Tests for the deterministic evidence checks and gate logic."""

from onramp_neuro_san import checks


def _ev(kind, facts=None, label=""):
    return {"kind": kind, "facts": facts or {}, "label": label}


FULL_CLEAN = [
    _ev("msa", {"liability_cap_multiple": 1.0}),
    _ev("sow", {"milestones": ["M1"]}),
    _ev("order_form", {"products": 2}),
    _ev("po", {"po_number": "PO-1", "po_matches_sow": True}),
    _ev("dpa", {"signed": True, "residency": "UK"}),
]


def test_clean_case_all_pass_and_gate_clear():
    results = checks.run_checks(FULL_CLEAN)
    summary = checks.summarise(results)
    assert summary["block"] == 0
    assert summary["review"] == 0
    assert summary["gate_clear"] is True


def test_missing_dpa_blocks():
    evidence = [e for e in FULL_CLEAN if e["kind"] != "dpa"]
    results = checks.run_checks(evidence)
    summary = checks.summarise(results)
    assert summary["open_blocks"] >= 1
    assert summary["gate_clear"] is False


def test_high_liability_cap_triggers_review():
    evidence = [
        _ev("msa", {"liability_cap_multiple": 3.0, "data_breach_indemnity": "uncapped"}),
        _ev("sow", {}),
        _ev("order_form", {}),
        _ev("po", {"po_number": "PO-9", "po_matches_sow": False}),
        _ev("dpa", {"signed": True, "residency": "EU"}),
    ]
    results = checks.run_checks(evidence)
    codes = {c["code"]: c["result"] for c in results}
    assert codes["msa_liability_cap"] == "REVIEW"
    assert codes["msa_breach_indemnity"] == "REVIEW"
    assert codes["po_matches_sow"] == "REVIEW"
    summary = checks.summarise(results)
    assert summary["gate_clear"] is False


def test_hold_does_not_clear_review():
    results = checks.run_checks([
        _ev("msa", {"liability_cap_multiple": 3.0}),
        _ev("sow", {}), _ev("order_form", {}),
        _ev("po", {"po_number": "P", "po_matches_sow": True}),
        _ev("dpa", {"signed": True, "residency": "UK"}),
    ])
    # Simulate a hold disposition on the review check.
    for c in results:
        if c["code"] == "msa_liability_cap":
            c["disposition"] = "hold"
    summary = checks.summarise(results)
    assert summary["open_reviews"] >= 1
    assert summary["gate_clear"] is False


def test_cleared_review_clears_gate():
    results = checks.run_checks([
        _ev("msa", {"liability_cap_multiple": 3.0}),
        _ev("sow", {}), _ev("order_form", {}),
        _ev("po", {"po_number": "P", "po_matches_sow": True}),
        _ev("dpa", {"signed": True, "residency": "UK"}),
    ])
    for c in results:
        if c["result"] == "REVIEW":
            c["disposition"] = "cleared"
    summary = checks.summarise(results)
    assert summary["open_reviews"] == 0
    assert summary["gate_clear"] is True

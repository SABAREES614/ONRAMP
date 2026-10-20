"""Deterministic evidence checks and gate logic for ONRAMP.

These are pure-Python rules over the structured evidence facts. They never call
an LLM. Each check yields one of three results:

* PASS   - requirement satisfied by structured facts
* REVIEW - ambiguous / exceeds playbook / missing structured fact: a named human
           must disposition it before the gate can clear
* BLOCK  - a required record is missing entirely; blocks the case until resolved

Per the README: missing structured contract or PO facts require human review;
they do not pass by default. A hold cannot clear a check.
"""

from __future__ import annotations

from typing import Any

# Corporate legal playbook (data, not code) - liability cap standard & fallback.
PLAYBOOK_CAP_STANDARD = 1.0
PLAYBOOK_CAP_FALLBACK = 1.5

REQUIRED_EVIDENCE = {
    "msa": "Executed MSA",
    "sow": "SOW",
    "order_form": "Order form",
    "po": "Purchase order",
    "dpa": "Data Processing Agreement",
}


def _by_kind(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Latest evidence record per kind."""
    out: dict[str, dict[str, Any]] = {}
    for ev in evidence:
        out[ev["kind"]] = ev
    return out


def run_checks(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run all deterministic checks over the case evidence."""
    found = _by_kind(evidence)
    results: list[dict[str, Any]] = []

    # 1. Required documents present.
    for kind, label in REQUIRED_EVIDENCE.items():
        if kind in found:
            results.append({
                "code": f"doc_present_{kind}",
                "title": f"{label} present",
                "result": "PASS",
                "detail": f"{label} record on file.",
            })
        else:
            results.append({
                "code": f"doc_present_{kind}",
                "title": f"{label} present",
                "result": "BLOCK",
                "detail": f"{label} is missing. Add the record and rerun checks.",
            })

    # 2. MSA liability cap vs playbook.
    msa = found.get("msa")
    if msa is None:
        results.append({
            "code": "msa_liability_cap",
            "title": "MSA liability cap within playbook",
            "result": "BLOCK",
            "detail": "No executed MSA to evaluate.",
        })
    else:
        cap = (msa.get("facts") or {}).get("liability_cap_multiple")
        if cap is None:
            results.append({
                "code": "msa_liability_cap",
                "title": "MSA liability cap within playbook",
                "result": "REVIEW",
                "detail": "Liability cap multiple not captured; counsel must confirm.",
            })
        elif cap <= PLAYBOOK_CAP_STANDARD:
            results.append({
                "code": "msa_liability_cap",
                "title": "MSA liability cap within playbook",
                "result": "PASS",
                "detail": f"Cap {cap}x ≤ playbook standard {PLAYBOOK_CAP_STANDARD}x.",
            })
        elif cap <= PLAYBOOK_CAP_FALLBACK:
            results.append({
                "code": "msa_liability_cap",
                "title": "MSA liability cap within playbook",
                "result": "REVIEW",
                "detail": (f"Cap {cap}x within pre-approved fallback "
                           f"{PLAYBOOK_CAP_FALLBACK}x; record counsel acceptance."),
            })
        else:
            results.append({
                "code": "msa_liability_cap",
                "title": "MSA liability cap within playbook",
                "result": "REVIEW",
                "detail": (f"Cap {cap}x exceeds playbook fallback "
                           f"{PLAYBOOK_CAP_FALLBACK}x; counsel must accept the risk."),
            })

        # 2b. Uncapped data-breach indemnity is a material deviation.
        indemnity = (msa.get("facts") or {}).get("data_breach_indemnity")
        if indemnity and str(indemnity).lower() == "uncapped":
            results.append({
                "code": "msa_breach_indemnity",
                "title": "Data-breach indemnity within cap",
                "result": "REVIEW",
                "detail": "Uncapped data-breach indemnity; counsel decision required.",
            })

    # 3. PO matches SOW.
    po = found.get("po")
    if po is None:
        results.append({
            "code": "po_matches_sow",
            "title": "Purchase order matches SOW",
            "result": "BLOCK",
            "detail": "No purchase order to reconcile.",
        })
    else:
        matches = (po.get("facts") or {}).get("po_matches_sow")
        if matches is True:
            results.append({
                "code": "po_matches_sow",
                "title": "Purchase order matches SOW",
                "result": "PASS",
                "detail": "PO reconciles to SOW milestones.",
            })
        elif matches is False:
            results.append({
                "code": "po_matches_sow",
                "title": "Purchase order matches SOW",
                "result": "REVIEW",
                "detail": "PO does not reconcile to SOW; finance must review.",
            })
        else:
            results.append({
                "code": "po_matches_sow",
                "title": "Purchase order matches SOW",
                "result": "REVIEW",
                "detail": "PO/SOW match not captured; finance must confirm.",
            })

    # 4. DPA residency where known.
    dpa = found.get("dpa")
    if dpa is not None:
        facts = dpa.get("facts") or {}
        if facts.get("signed") and facts.get("residency"):
            results.append({
                "code": "dpa_residency",
                "title": "DPA signed with residency",
                "result": "PASS",
                "detail": f"DPA signed; residency {facts.get('residency')}.",
            })
        else:
            results.append({
                "code": "dpa_residency",
                "title": "DPA signed with residency",
                "result": "REVIEW",
                "detail": "DPA present but signature/residency not confirmed.",
            })

    return results


def summarise(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate counts and whether the gate is clear for approval."""
    blocks = [c for c in checks if c["result"] == "BLOCK"]
    reviews = [c for c in checks if c["result"] == "REVIEW"]
    passes = [c for c in checks if c["result"] == "PASS"]

    # A BLOCK is cleared only by resolving the underlying evidence (rerun),
    # never by disposition. A REVIEW clears only with an explicit 'cleared'
    # disposition; a 'hold' does NOT clear it.
    open_blocks = blocks  # blocks never clear via disposition
    open_reviews = [c for c in reviews if c.get("disposition") != "cleared"]
    failed = [c for c in checks if c.get("disposition") == "failed"]

    gate_clear = not open_blocks and not open_reviews and not failed
    return {
        "pass": len(passes),
        "review": len(reviews),
        "block": len(blocks),
        "open_blocks": len(open_blocks),
        "open_reviews": len(open_reviews),
        "failed": len(failed),
        "gate_clear": gate_clear,
    }

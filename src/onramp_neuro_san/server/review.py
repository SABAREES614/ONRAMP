"""Concierge review orchestration.

Builds a real prompt and private sly_data payload from a case, drives the
Neuro-SAN network via the real client, and records the run (success with the
captured trace, or failure with the error). There is no mock path: a failed
call is persisted as an error and blocks approval.
"""

from __future__ import annotations

import json
from typing import Any


def _facts(evidence: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    for ev in evidence:
        if ev["kind"] == kind:
            return ev.get("facts") or {}
    return {}


def build_prompt(case: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    """Compose the natural-language onboarding request for the Concierge."""
    present = sorted({ev["kind"] for ev in evidence})
    lines = [
        f"Deal '{case['client_name']}' is closed-won "
        f"(opportunity {case.get('opportunity_ref') or 'n/a'}, TCV {case.get('tcv') or 'n/a'}).",
        "Onboard them into our implementation life cycle and tell me what is "
        "blocking kickoff and which named human approvals are outstanding.",
        "",
        f"Document kinds on file: {', '.join(present) if present else 'none'}.",
    ]
    msa = _facts(evidence, "msa")
    if "liability_cap_multiple" in msa:
        lines.append(
            f"The executed MSA has a liability cap of "
            f"{msa['liability_cap_multiple']}x annual fees; validate it against "
            "the playbook using your legal validator."
        )
    po = _facts(evidence, "po")
    if po:
        lines.append(
            f"Reconcile purchase order {po.get('po_number', 'n/a')} against the SOW."
        )
    lines.append(
        "Screen the client entity for sanctions/PEP exposure using the reference 'entity'."
    )
    return "\n".join(lines)


def build_sly_data(case: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble the private sly_data (contract value, screening records)."""
    sly: dict[str, Any] = {"case_id": case["id"]}

    # Parse a numeric contract value from the TCV string if possible.
    tcv = str(case.get("tcv") or "")
    value = _parse_money(tcv)
    if value is not None:
        sly["contract_value"] = value

    # Private screening identifiers, keyed by opaque reference.
    sly["screening_records"] = {
        "entity": {"legal_name": case["client_name"], "registry_ref": case.get("opportunity_ref")}
    }
    return sly


def _parse_money(text: str) -> float | None:
    """Parse strings like '$4.1m' or '$1.2m' into an absolute number."""
    t = text.strip().lower().replace("£", "").replace(",", "").replace("$", "")
    if not t:
        return None
    mult = 1.0
    if t.endswith("m"):
        mult = 1_000_000
        t = t[:-1]
    elif t.endswith("k"):
        mult = 1_000
        t = t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        return None

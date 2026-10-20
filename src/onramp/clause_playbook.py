# Copyright 2026 ONRAMP (hackathon build on neuro-san, Apache-2.0).
"""Clause playbook comparator (deterministic).

Compares an executed MSA liability-cap multiple against the corporate legal
playbook and computes the cap *amount* from the contract value. The contract
value is read from ``sly_data`` so the figure never enters the LLM prompt;
only the resulting multiple classification and a rounded exposure band are
returned to the chat stream.
"""

from __future__ import annotations

from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

PLAYBOOK_CAP_STANDARD = 1.0
PLAYBOOK_CAP_FALLBACK = 1.5


class ClausePlaybook(CodedTool):
    """Deterministic clause comparison against the playbook."""

    async def async_invoke(self, args: Dict[str, Any],
                           sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        cap_multiple = args.get("liability_cap_multiple")
        if cap_multiple is None:
            return {
                "status": "review",
                "reason": "No liability cap multiple provided; counsel must confirm.",
            }
        try:
            cap_multiple = float(cap_multiple)
        except (TypeError, ValueError):
            return {"status": "review", "reason": "Liability cap multiple not numeric."}

        # contract_value kept in sly_data (private); never echoed in full.
        contract_value = sly_data.get("contract_value")
        cap_amount_band = None
        if contract_value is not None:
            try:
                amount = float(contract_value) * cap_multiple
                # Return only a coarse band, not the exact figure.
                cap_amount_band = _band(amount)
            except (TypeError, ValueError):
                cap_amount_band = None

        if cap_multiple <= PLAYBOOK_CAP_STANDARD:
            classification = "within_standard"
            recommendation = "Proceed; cap within playbook standard."
        elif cap_multiple <= PLAYBOOK_CAP_FALLBACK:
            classification = "within_fallback"
            recommendation = "Record counsel acceptance of pre-approved fallback."
        else:
            classification = "beyond_fallback"
            recommendation = "Counsel must accept the risk; log playbook gap."

        return {
            "status": "ok",
            "liability_cap_multiple": cap_multiple,
            "playbook_standard": PLAYBOOK_CAP_STANDARD,
            "playbook_fallback": PLAYBOOK_CAP_FALLBACK,
            "classification": classification,
            "exposure_band": cap_amount_band,
            "recommendation": recommendation,
        }


def _band(amount: float) -> str:
    if amount < 1_000_000:
        return "<$1m"
    if amount < 5_000_000:
        return "$1m-$5m"
    if amount < 10_000_000:
        return "$5m-$10m"
    return ">$10m"

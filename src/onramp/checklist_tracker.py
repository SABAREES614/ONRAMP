# Copyright 2026 ONRAMP (hackathon build on neuro-san, Apache-2.0).
"""Evidence checklist tracker (deterministic).

Given the set of evidence kinds present on a case, reports completeness and
which required documents are still missing. No LLM, no sensitive data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from neuro_san.interfaces.coded_tool import CodedTool

REQUIRED = {
    "msa": "Executed MSA",
    "sow": "SOW",
    "order_form": "Order form",
    "po": "Purchase order",
    "dpa": "Data Processing Agreement",
}


class ChecklistTracker(CodedTool):
    """Reports onboarding document checklist completeness."""

    async def async_invoke(self, args: Dict[str, Any],
                           sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        present: List[str] = args.get("present_kinds") or []
        if isinstance(present, str):
            present = [p.strip() for p in present.split(",") if p.strip()]
        present_set = {p.lower() for p in present}

        missing = [label for kind, label in REQUIRED.items()
                   if kind not in present_set]
        complete = len(missing) == 0
        pct = round((len(REQUIRED) - len(missing)) / len(REQUIRED) * 100)

        return {
            "status": "ok",
            "complete": complete,
            "completeness_pct": pct,
            "missing": missing,
            "required": list(REQUIRED.values()),
        }

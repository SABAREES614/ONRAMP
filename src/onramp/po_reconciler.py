# Copyright 2026 ONRAMP (hackathon build on neuro-san, Apache-2.0).
"""PO / SOW reconciliation (deterministic)."""

from __future__ import annotations

from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool


class PoReconciler(CodedTool):
    """Reconciles a purchase order against SOW milestones."""

    async def async_invoke(self, args: Dict[str, Any],
                           sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        po_number = args.get("po_number")
        matches = args.get("po_matches_sow")

        if po_number is None:
            return {"status": "block", "reason": "No purchase order provided."}
        if matches is True:
            return {"status": "pass", "po_number": po_number,
                    "reason": "PO reconciles to SOW milestones."}
        if matches is False:
            return {"status": "review", "po_number": po_number,
                    "reason": "PO does not reconcile to SOW; finance review required."}
        return {"status": "review", "po_number": po_number,
                "reason": "PO/SOW match not captured; finance must confirm."}

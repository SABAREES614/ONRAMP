# Copyright 2026 ONRAMP (hackathon build on neuro-san, Apache-2.0).
"""Compliance screening (deterministic).

Screens a subject (entity or UBO) for sanctions/PEP exposure. Identity details
(name, DOB, passport) are held in ``sly_data`` keyed by an opaque reference; the
LLM only ever sees the reference and the resulting match score, never the
identifiers. A score at/above the threshold routes to human review.

This build computes a deterministic, reproducible score from the reference so
the demo is self-contained; in production the same interface would wrap a
vendor screening API, with the key read from a secret store / sly_data.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

MATCH_THRESHOLD = 0.85


class ComplianceScreen(CodedTool):
    """Deterministic sanctions/PEP screening returning a score only."""

    async def async_invoke(self, args: Dict[str, Any],
                           sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        subject_ref = args.get("subject_ref")
        if not subject_ref:
            return {"status": "error", "reason": "subject_ref is required"}

        # Identifiers live in sly_data; used only to compute a score.
        records = sly_data.get("screening_records") or {}
        person = records.get(subject_ref)

        score = self._score(subject_ref, person)
        status = "clear" if score < MATCH_THRESHOLD else "human_review"
        return {
            "status": status,
            "subject_ref": subject_ref,
            "match_score": round(score, 2),
            "threshold": MATCH_THRESHOLD,
            "decision": ("auto_clear" if status == "clear"
                         else "route_to_compliance_officer"),
        }

    @staticmethod
    def _score(subject_ref: str, person: Any) -> float:
        basis = subject_ref if person is None else f"{subject_ref}:{person}"
        digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
        # Map first 4 hex chars to [0, 1).
        return int(digest[:4], 16) / 0xFFFF

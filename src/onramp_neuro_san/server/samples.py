"""Sample onboarding documents for first-time users.

Generates fictional, illustrative sample files (plain-text) for each evidence
kind so a new user can download them, inspect the expected content, and upload
them on the Case workspace. All content is fictional. Currency is shown in $.
"""

from __future__ import annotations

SAMPLES: dict[str, dict[str, str]] = {
    "msa": {
        "filename": "sample_executed_MSA.txt",
        "title": "Master Services Agreement (sample)",
        "body": """MASTER SERVICES AGREEMENT (SAMPLE — FICTIONAL)

Parties:        Acme Services Ltd ("Supplier") and Northwind Logistics ("Client")
Effective date: 2026-01-15
Term:           12 months, auto-renew annually

1. Services. Supplier provides the services described in each SOW.
2. Fees. As set out in the applicable Order Form. Annual fees: $1,200,000.
3. Limitation of liability. Each party's aggregate liability is capped at
   1x the annual fees (playbook standard).
4. Data-breach indemnity. Within the general liability cap.
5. Governing law. England & Wales.
6. Confidentiality. 5 years post-termination.

STRUCTURED FACTS (for onboarding entry):
  liability_cap_multiple = 1.0
  governing_law          = England & Wales

This is a fictional sample for demonstration only. Do not use as a real contract.
""",
    },
    "sow": {
        "filename": "sample_SOW-01.txt",
        "title": "Statement of Work (sample)",
        "body": """STATEMENT OF WORK — SOW-01 (SAMPLE — FICTIONAL)

Client:    Northwind Logistics
Project:   Implementation of the logistics platform
Milestones:
  M1 — Discovery & design           (weeks 1-2)
  M2 — Build & integration          (weeks 3-6)
  M3 — UAT & training               (weeks 7-8)
  M4 — Go-live & hypercare          (week 8+)

Acceptance: milestone sign-off by the Client delivery lead.

STRUCTURED FACTS (for onboarding entry):
  milestones = ["M1", "M2", "M3", "M4"]

Fictional sample for demonstration only.
""",
    },
    "order_form": {
        "filename": "sample_order_form.txt",
        "title": "Order Form (sample)",
        "body": """ORDER FORM (SAMPLE — FICTIONAL)

Client:   Northwind Logistics
Products: 2
  1. Logistics Platform — Standard tier
  2. Analytics Add-on
Term:     12 months
Total contract value: $1,200,000

STRUCTURED FACTS (for onboarding entry):
  products = 2

Fictional sample for demonstration only.
""",
    },
    "po": {
        "filename": "sample_purchase_order.txt",
        "title": "Purchase Order (sample)",
        "body": """PURCHASE ORDER (SAMPLE — FICTIONAL)

PO number:  PO-7781
Client:     Northwind Logistics
References: SOW-01, Order Form
Amount:     $1,200,000
Matches SOW milestones: YES

STRUCTURED FACTS (for onboarding entry):
  po_number      = PO-7781
  po_matches_sow = true

Fictional sample for demonstration only.
""",
    },
    "dpa": {
        "filename": "sample_DPA.txt",
        "title": "Data Processing Agreement (sample)",
        "body": """DATA PROCESSING AGREEMENT (SAMPLE — FICTIONAL)

Controller:         Northwind Logistics
Processor:          Acme Services Ltd
Signed:             YES (2026-01-15)
Data residency:     UK
Transfer mechanism: Standard Contractual Clauses
Sub-processors:     Listed in Annex A

STRUCTURED FACTS (for onboarding entry):
  signed    = true
  residency = UK

Fictional sample for demonstration only.
""",
    },
}

ORDER = ["msa", "sow", "order_form", "po", "dpa"]


def list_samples() -> list[dict[str, str]]:
    """Return sample metadata for the UI (kind, filename, title)."""
    return [{"kind": k, "filename": SAMPLES[k]["filename"], "title": SAMPLES[k]["title"]}
            for k in ORDER]


def get_sample(kind: str) -> dict[str, str] | None:
    return SAMPLES.get(kind)

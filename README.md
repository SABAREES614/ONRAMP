# ONRAMP

ONRAMP turns a closed-won deal into a governed onboarding case. This local hackathon build covers the complete eight-stage flow: deal handoff, document collection, compliance, legal review, commercial approval, mobilisation/access, kickoff, and hypercare to first value. It includes case management, structured evidence, deterministic Python checks, a Neuro-SAN network with the Concierge and eight specialist agents, named human gates, kickoff readiness, and a case audit history.

The source architecture prototype includes external integrations and broader architecture, economics, and evaluation screens. Their exact coverage status is mapped in [docs/PROTOTYPE_COVERAGE.md](docs/PROTOTYPE_COVERAGE.md). Do not treat planned integrations as live.

## Open and install on Windows

Open the project folder in VS Code. Install Python 3.12, [uv](https://docs.astral.sh/uv/), and [Node.js](https://nodejs.org/) (for the optional front-end syntax check). No local model runtime is required — ONRAMP uses remote, OpenAI-compatible LLM providers (Hugging Face, NVIDIA, OpenRouter, or OpenAI).

In PowerShell at the project root:

```powershell
uv python install 3.12
uv sync --extra dev --link-mode copy
Copy-Item .env.example .env   # optional; the Settings page can write this for you
```

The first dependency download needs internet access.

### LLM provider & API keys

ONRAMP talks to a remote provider through the Neuro-SAN `llm_config` mechanism. You configure the provider, model and API key on the in-app **Settings · API keys** page (nav → Configure), which writes them to the git-ignored `.env`. Keys are masked in the UI, never echoed, and delivered to agents via the private `sly_data` channel — they never appear in a prompt.

Supported providers (choose one on the Settings page):

- **Hugging Face (Inference Router):** neuro-san `openai` class against `https://router.huggingface.co/v1`. Token: <https://huggingface.co/settings/tokens>. Example model `meta-llama/Llama-3.3-70B-Instruct`.
- **NVIDIA (build.nvidia.com / NIM):** native `nvidia` class against `https://integrate.api.nvidia.com/v1`. Key: <https://build.nvidia.com>. Example model `meta/llama-3.3-70b-instruct`.
- **OpenRouter:** native `openrouter` class. Key: <https://openrouter.ai/keys>. Example model `openrouter/auto`.
- **OpenAI (or OpenAI-compatible):** `openai` class. Key: <https://platform.openai.com/api-keys>.

Pick a model that supports tool calling (the Concierge front-man and branch agents require tools). There are no dummy or simulated LLM calls: if no key is set, or the Neuro-SAN network is unreachable, a Concierge review fails, the error is recorded, and the case cannot be approved.

## Start the local services

Open two PowerShell terminals at the project root. (If `uv` is not on your PATH, prepend it: `$env:Path = "$HOME\.local\bin;$env:Path"`.)

**Terminal 1 — Neuro-SAN server (ONRAMP network):**

```powershell
$env:AGENT_MANIFEST_FILE = (Resolve-Path .\registries\manifest.hocon).Path
$env:AGENT_TOOL_PATH = (Resolve-Path .\src).Path
uv run ns run --server-only --server-host 127.0.0.1 --server-http-port 8080
```

Or simply run `.\run_neuro_san.ps1`. The served network is `onramp/onramp_onboarding` (the Concierge plus eight specialists and four deterministic Python coded tools). Neuro-SAN Studio 0.4.2 is pinned by the project. Evidence policy checks run separately as deterministic Python code.

**Terminal 2 — ONRAMP app:**

```powershell
uv run uvicorn onramp_neuro_san.server.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The health endpoint is <http://127.0.0.1:8000/api/health> (it reports whether the Neuro-SAN server is reachable and whether a provider key is configured); API documentation is at <http://127.0.0.1:8000/docs>. Cases, evidence metadata and audit events live in `data/onramp.db`; uploaded files are stored under `data/uploads/`. These local files are not encrypted or access-controlled.

## Walk through the complete process

All starter clients and records are fictional.

1. In **Portfolio**, open Northwind Logistics or create a closed-won case. The handoff form captures opportunity reference, delivery owner, stakeholder roles (no contact details), and commercial commitments.
2. In **Case workspace**, either enter the five evidence records (executed MSA, SOW, order form, purchase order, and DPA) or attach source files locally. Uploads accept PDF, DOC, DOCX, or UTF-8 TXT up to 15 MB and can be downloaded from the case. The app stores a SHA-256 fingerprint; it does not run malware scanning, OCR, text extraction, signature verification, or classification. Enter the stated MSA cap multiple, PO/SOW match, and DPA residency where known, then run deterministic evidence checks. Missing structured contract or PO facts require human review; they do not pass by default.
3. Run **Concierge review**. This calls the configured Neuro-SAN network through your selected remote provider. Open the raw trace and review the actual response. If the call fails or times out, the case records the failure and cannot be approved.
4. Open **Lifecycle board**. Record the handoff sign-off. Document collection completes from the five received evidence records. Then record the named compliance, counsel, and finance sign-offs in order. After a completed agent review and clear checks, record mobilisation/access readiness.
5. In **Human review**, disposition every REVIEW check with a named reviewer and rationale. A hold cannot clear a check. Approve kickoff only when all BLOCK checks are resolved, all REVIEW checks have a human clearance, the real Neuro-SAN run completed, and lifecycle sign-offs are recorded.
6. Back on **Lifecycle board**, record that the kickoff was held and later record the first-value milestone and lessons. Each action appears in the case audit history.

For an exception path, open **Orion Retail Group**: its 3x MSA cap and flagged evidence require counsel review. **Helix Bank plc** demonstrates a missing DPA and stays blocked until the missing record is added and checks are rerun. Evidence edits invalidate downstream reviews and sign-offs.

Lifecycle sign-offs are named text attestations for this local demo; there is no authentication or role verification. They do not claim that CRM, registry screening, ERP, project, identity, or email integrations ran.

## Validate the project

```powershell
uv run ns validate .\registries\onramp\onramp_onboarding.hocon --registry-dir . --manifest .\registries\manifest.hocon --verbose
uv run python -m compileall src tests
uv run pytest -q
```

Check inline JavaScript syntax with Node:

```powershell
node -e "const fs=require('fs');const s=fs.readFileSync('frontend/index.html','utf8');const js=s.match(/<script>([\s\S]*?)<\/script>/)[1];new Function(js);console.log('inline JavaScript syntax OK')"
```

## Scope and limits

- **Implemented:** local case intake and handoff, evidence capture and deterministic rules, eight-stage lifecycle, eight fact-routed Neuro-SAN specialist definitions plus Concierge, actual result/trace capture on successful calls, local document attachments with hashes, human review, server-side approval gates, kickoff-held and first-value records, and SQLite audit history.
- **Planned:** live CRM/Agentforce handoff, OCR/document extraction and classification, malware scanning, KYB/sanctions/PEP sources, full legal clause extraction, ERP billing, project provisioning, identity/access setup, client message sending, authentication, production policy enforcement, immutable audit retention, and cloud deployment.
- **Demonstrative or partial:** multi-cloud diagrams, ROI/technical-debt comparisons, framework positioning, scripted portfolio scenarios, and probabilistic fixture scorecards. See the coverage checklist for the full list.

This is a local hackathon build, not a production-ready compliance system. Do not enter real client personal, tax, or banking data or upload real confidential agreements.

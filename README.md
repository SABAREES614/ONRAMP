# ONRAMP

ONRAMP turns a closed-won deal into a governed onboarding case. This local hackathon build covers the complete eight-stage flow: deal handoff, document collection, compliance, legal review, commercial approval, mobilisation/access, kickoff, and hypercare to first value. It includes case management, structured evidence, deterministic Python checks, a Neuro-SAN network with the Concierge and eight specialist agents, named human gates, kickoff readiness, and a case audit history.

The source architecture prototype includes external integrations and broader architecture, economics, and evaluation screens. Their exact coverage status is mapped in [docs/PROTOTYPE_COVERAGE.md](docs/PROTOTYPE_COVERAGE.md). Do not treat planned integrations as live.

## Open and install on Windows

Open `C:\Users\sabar\OneDrive\Desktop\ONRAMP` in VS Code. Install Python 3.12, [uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org/) for the optional front-end syntax check, and [Ollama](https://ollama.com/download/windows).

In PowerShell at the project root:

```powershell
uv python install 3.12
uv sync --extra dev --link-mode copy
Copy-Item .env.example .env

# Pull the selected model (NVIDIA Nemotron-3-Nano 4B):
ollama pull nemotron-3-nano:4b

# Or pull the verified baseline model (Qwen3 8B):
ollama pull qwen3:8b
```

The first dependency and model downloads need internet access. Local inference uses no paid model API. 

### Local Model Selection & Switching

ONRAMP supports any local Ollama model via the `ONRAMP_MODEL` setting in `.env` or the environment:
- **NVIDIA Nemotron-3-Nano (4B):** Set `ONRAMP_MODEL=nemotron-3-nano:4b`. Optimized for low VRAM, high throughput, and tool calling. Download with `ollama pull nemotron-3-nano:4b` (2.8 GB).
- **Qwen3 (8B) Baseline:** Set `ONRAMP_MODEL=qwen3:8b`. Fully tested baseline model with an actual 18-event trace and tool verification on local CPU.

To switch models:
1. Update `ONRAMP_MODEL` in `.env` (e.g. `ONRAMP_MODEL=nemotron-3-nano:4b` or `ONRAMP_MODEL=qwen3:8b`).
2. Restart Neuro-SAN and ONRAMP (see Terminal commands below) so the new setting is loaded into HOCON.

If `Copy-Item` reports that `.env` already exists, keep the existing local settings. To use a different installed Ollama model, set `ONRAMP_MODEL` in `.env` before starting Neuro-SAN and ONRAMP.

OpenRouter is optional. Create your own API key on [OpenRouter](https://openrouter.ai/keys), then add `ONRAMP_LLM_CLASS=openai`, `ONRAMP_MODEL=openrouter/free`, and `OPENROUTER_API_KEY=your-key` to the local `.env`. The HOCON routes the installed Neuro-SAN `openai` adapter to OpenRouter's OpenAI-compatible endpoint. Keep the key private and out of chat, source control, screenshots, and logs. `openrouter/free` currently routes requests to available free models, but capacity and model availability can change; confirm current limits on [OpenRouter's free models page](https://openrouter.ai/collections/free-models/). Requests leave the machine in this mode. Ollama remains the default and is fully local.

## Start the local services

Open three VS Code PowerShell terminals, all at the project root.

**Terminal 1 - Ollama** (Ollama Desktop normally starts the local service automatically):

```powershell
ollama serve
```

If Ollama is already running, leave it running and check the installed model with `ollama list`. You may also start the model with `ollama run qwen3:8b`.

**Terminal 2 - Neuro-SAN Studio:**

```powershell
$env:AGENT_MANIFEST_FILE = (Resolve-Path .\registries\manifest.hocon).Path
$env:AGENT_TOOL_PATH = (Resolve-Path .\src).Path
uv run ns run --server-host 127.0.0.1 --server-http-port 8080 --nsflow-port 4173
```

The network is `registries/onramp/onramp_onboarding.hocon`. Neuro-SAN Studio 0.4.2 is pinned by the project. The visual agent inspector is served at http://localhost:4173. The registry defines the Concierge plus all eight prototype specialists; evidence policy checks run separately as deterministic Python code.

**Terminal 3 - ONRAMP:**

```powershell
uv run uvicorn onramp_neuro_san.server.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The local health endpoint is <http://127.0.0.1:8000/api/health>; API documentation is at <http://127.0.0.1:8000/docs>. Cases, evidence metadata and audit events live in `data/onramp.db`; uploaded files are stored under `data/uploads/`. These local files are not encrypted or access-controlled.

## Walk through the complete process

All starter clients and records are fictional.

1. In **Portfolio**, open Northwind Logistics or create a closed-won case. The handoff form captures opportunity reference, delivery owner, stakeholder roles (no contact details), and commercial commitments.
2. In **Case workspace**, either enter the five evidence records (executed MSA, SOW, order form, purchase order, and DPA) or attach source files locally. Uploads accept PDF, DOC, DOCX, or UTF-8 TXT up to 15 MB and can be downloaded from the case. The app stores a SHA-256 fingerprint; it does not run malware scanning, OCR, text extraction, signature verification, or classification. Enter the stated MSA cap multiple, PO/SOW match, and DPA residency where known, then run deterministic evidence checks. Missing structured contract or PO facts require human review; they do not pass by default.
3. Run **Concierge review**. This calls the configured Neuro-SAN network through local Ollama. Open the raw trace and review the actual response. If the call fails or times out, the case records the failure and cannot be approved.
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

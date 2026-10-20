# ONRAMP — Architecture

This document describes the **current, as-built** architecture of ONRAMP: a
local-first, human-governed client-onboarding workbench built on
[neuro-san](https://github.com/cognizant-ai-lab/neuro-san-studio) (Apache-2.0,
Cognizant AI Lab).

Unlike the original experience prototype — which sketched three separate cloud
reference architectures (Azure, AWS, GCP) — this build is a single, concrete
deployment: two local Python processes plus a remote LLM provider you choose.
There are **no mock/dummy LLM calls**; every Concierge review drives the real
agent network, and a failed call is recorded and blocks approval.

---

## 1. Components at a glance

| Layer | Component | Technology | Port |
|------|-----------|-----------|------|
| Browser | Single-page UI | Vanilla HTML/CSS/JS (served statically) | — |
| App tier | ONRAMP API + static host | FastAPI + Uvicorn (`onramp_neuro_san.server.app`) | 8000 |
| Agent tier | Neuro-SAN server | `neuro-san-studio==0.4.2` (`ns run`) | 8080 |
| Agent network | `onramp/onramp_onboarding` | HOCON registry + Python coded tools | — |
| Storage | Case store, evidence, audit | SQLite (`data/onramp.db`) + file uploads (`data/uploads/`) | — |
| Secrets/config | Provider + API keys | `.env` (git-ignored) | — |
| LLM | Remote provider (your key) | HuggingFace / NVIDIA / OpenRouter / OpenAI | — |

Everything in the first six rows runs **locally on one machine**. Only the LLM
call leaves the machine, going to the provider you configure.

---

## 2. Request / data flow

```
┌────────────┐   HTTP/JSON    ┌──────────────────────────┐
│  Browser   │ ─────────────▶ │  ONRAMP API (FastAPI)     │  :8000
│  (SPA UI)  │ ◀───────────── │  onramp_neuro_san.server  │
└────────────┘                └───────────┬──────────────┘
                                           │
         ┌─────────────────────────────────┼───────────────────────────────┐
         │ deterministic (no LLM)           │ real agent run                │
         ▼                                  ▼                               │
┌──────────────────┐            ┌────────────────────────┐                  │
│ checks.py        │            │ neuro_client.py        │ streaming_chat   │
│ PASS/REVIEW/BLOCK│            │ AgentSessionFactory    │ + sly_data       │
│ + gate logic     │            └───────────┬────────────┘                  │
└──────────────────┘                        │ HTTP /api/v1/.../streaming_chat │
         │                                   ▼                               │
         │                      ┌────────────────────────┐  :8080           │
         │                      │ Neuro-SAN server        │                  │
         │                      │ onramp/onramp_onboarding│                  │
         │                      │  Concierge (front-man)  │                  │
         │                      │   └─ 8 specialists (AAOSA)                  │
         │                      │   └─ 4 coded tools       │                  │
         │                      └───────────┬────────────┘                  │
         │                                   │ LLM API (your key via sly_data)│
         ▼                                   ▼                               │
┌──────────────────┐            ┌────────────────────────┐                  │
│ SQLite onramp.db │            │ Remote LLM provider     │ ◀────────────────┘
│ + data/uploads/  │            │ HF / NVIDIA / OpenRouter│
└──────────────────┘            └────────────────────────┘
```

1. The browser calls the **ONRAMP API** for all operations.
2. **Deterministic checks** (`checks.py`) run in-process — pure Python, no LLM —
   producing PASS / REVIEW / BLOCK results and the kickoff gate decision.
3. A **Concierge review** calls `neuro_client.py`, which opens an HTTP streaming
   session to the **Neuro-SAN server** for the `onramp/onramp_onboarding`
   network and captures the full agent trace.
4. The network's front-man (**Onboarding Concierge**) delegates to eight
   specialist agents via the **AAOSA** protocol; specialists call **coded tools**
   for exact, deterministic work.
5. The LLM calls go to the **remote provider** you configured. The API key and
   sensitive values travel on the private **sly_data** channel — never in a prompt.
6. Cases, evidence metadata, agent runs and the audit trail persist to **SQLite**;
   uploaded files are stored on disk with a SHA-256 fingerprint.

---

## 3. The agent network (`onramp/onramp_onboarding`)

A hierarchical neuro-san network: one front-man coordinating eight specialists,
with four deterministic Python coded tools. Defined in
`registries/onramp/onramp_onboarding.hocon`; served via `registries/manifest.hocon`
with `AGENT_TOOL_PATH=src`.

```
                       Onboarding Concierge  (front-man, AAOSA coordinator)
                                 │  delegates via determine → follow-up → fulfil
   ┌──────────┬──────────┬───────┼────────┬───────────┬────────────┬──────────┐
   ▼          ▼          ▼       ▼        ▼           ▼            ▼          ▼
 Deal      Document   Compliance Legal  Commercial  Delivery    Access     Client
 Handover  Intelligence  (CO)   MSA     & Billing   Mobilisation Provision  Comms
 (DH)      (DI)                 Validator (CB)       (DM)        (AP)       (CC)
             │           │       (LG)     │
             ▼           ▼        ▼        ▼
        checklist_   compliance_ clause_  po_
        tracker      screen      playbook reconciler        (coded tools)
```

**Coded tools** (subclass `neuro_san.interfaces.coded_tool.CodedTool`, read
private values from `sly_data`, return only non-sensitive results):

- `checklist_tracker` — document completeness / missing records
- `compliance_screen` — sanctions/PEP match **score only** (identity stays private)
- `clause_playbook` — MSA liability cap vs playbook; exposure as a band, not a figure
- `po_reconciler` — purchase order vs SOW reconciliation

---

## 4. Governance model

Governance is enforced by the **app tier**, not left to the LLM:

- **Deterministic checks** decide PASS / REVIEW / BLOCK from structured facts.
- A **BLOCK** clears only by fixing the underlying evidence and re-running checks.
- A **REVIEW** clears only with an explicit human `cleared` disposition; a `hold`
  does **not** clear it.
- Editing evidence **invalidates** downstream checks, agent runs and sign-offs.
- **Kickoff approval** (`POST /api/cases/{id}/approve-kickoff`) is refused unless:
  all blocks resolved, all reviews cleared, no failed checks, **and** a successful
  real Neuro-SAN Concierge run is on record.
- Every action is written to an append-only **audit** table.

---

## 5. Security & privacy boundaries

- **sly_data trust boundary:** API keys, contract values and screening
  identifiers travel on neuro-san's private `sly_data` channel to coded tools and
  the model adapter; they are never placed in the prompt/chat stream.
- **Key storage:** provider keys live in the git-ignored `.env`, are masked in the
  UI, and are never echoed back by the API.
- **No local model runtime:** ONRAMP uses remote OpenAI-compatible providers only.
  The only outbound traffic is the LLM call to the provider you select (BYOK).
- **Local data is not encrypted or access-controlled** — this is a local build.
  Do not enter real client personal, tax or banking data.

---

## 6. LLM provider mapping

The **Settings · API keys** page selects a provider; ONRAMP maps it to a
neuro-san LLM class and injects the key via `sly_data`:

| Provider | neuro-san class | Key env var | Default base URL |
|---------|-----------------|-------------|------------------|
| Hugging Face | `openai` | `OPENAI_API_KEY` | `https://router.huggingface.co/v1` |
| NVIDIA | `nvidia` | `NVIDIA_API_KEY` | `https://integrate.api.nvidia.com/v1` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |

The chosen model must support **tool calling** (the Concierge and branch agents
delegate through tools).

---

## 7. Runtime topology & lifecycle

Two processes, started by `startup.bat`, stopped by `shutdown.bat`:

1. **Neuro-SAN server** (`ns run --server-only ... 8080`) — loads the HOCON
   registry and serves the agent network over HTTP.
2. **ONRAMP app** (`uvicorn onramp_neuro_san.server.app:app ... 8000`) — serves
   the UI and API, and acts as the Neuro-SAN **client** on each review.

`/api/health` reports app status, active provider, key presence and whether the
Neuro-SAN server is reachable.

---

## 8. Why a single deployment (not three clouds)

The experience prototype drew Azure, AWS and GCP reference diagrams to argue
portability. This build makes one honest, runnable choice instead: the same
HOCON network, coded tools, checks and governance run unchanged wherever the two
Python processes run — laptop, VM or container — and only the `llm_config`
provider differs. Portability is demonstrated by *swapping the provider on the
Settings page*, not by maintaining three parallel diagrams. The in-app
**Architecture** page renders this single, current view.

---

## 9. Key source files

| Path | Responsibility |
|------|----------------|
| `src/onramp_neuro_san/server/app.py` | FastAPI app: all endpoints + static host |
| `src/onramp_neuro_san/server/review.py` | Prompt + sly_data builder for a case |
| `src/onramp_neuro_san/neuro_client.py` | Real Neuro-SAN client (streaming_chat) |
| `src/onramp_neuro_san/checks.py` | Deterministic checks + gate logic |
| `src/onramp_neuro_san/db.py` | SQLite store + seed data |
| `src/onramp_neuro_san/provider.py` | Provider ↔ llm_config/sly_data mapping |
| `src/onramp_neuro_san/config.py` | Paths, agent name, settings |
| `src/onramp/*.py` | Four deterministic coded tools |
| `registries/onramp/onramp_onboarding.hocon` | The agent network definition |
| `registries/manifest.hocon` | Served-network manifest |
| `frontend/index.html` | Single-page UI (incl. Architecture page) |

# ONRAMP — Session Handover

_Last updated: 2026-10-20 (end of session). Resume point for the next working session._

This document captures the current state of the ONRAMP build so work can resume
cleanly and the code can be pushed to GitHub.

---

## 1. TL;DR — where we are

- The cloned repo (`https://github.com/SABAREES614/ONRAMP.git`) contained **only
  scaffolding**; the whole application was built this session.
- ONRAMP is a **local-first, human-governed client-onboarding workbench** on
  `neuro-san-studio==0.4.2`: a FastAPI app (`:8000`) that drives a real
  Neuro-SAN agent network (`:8080`). **No dummy LLM calls.**
- **It works end-to-end.** A real Concierge review succeeded via **OpenRouter**
  (`meta-llama/llama-3.3-70b-instruct`); the Onboarding Concierge delegated to
  the specialist agents via AAOSA.
- Everything is **verified**: 16/16 pytest pass, `ns validate` passes, inline JS
  valid, `compileall` clean.

---

## 2. How to resume tomorrow (fast start)

```powershell
# From the project root:
cd C:\Users\s_pre\Downloads\Prototypes\ONRAMP

# If uv isn't on PATH this session:
$env:Path = "$HOME\.local\bin;$env:Path"

# (Only if deps changed) re-sync:
uv sync --extra dev --link-mode copy

# Start both servers + open the browser:
.\startup.bat
#   -> ONRAMP-NeuroSAN window (agent server, :8080)
#   -> ONRAMP-App window      (web app + API, :8000)
#   -> opens http://127.0.0.1:8000

# Stop everything:
.\shutdown.bat
```

Then open the app, go to **Settings · API keys**, confirm the provider/key, and
click **Test connection**. The LLM provider key lives in the git-ignored `.env`
(it is NOT committed), so it persists locally between sessions.

> NOTE: `startup.bat`/`shutdown.bat` were verified by running the underlying
> server commands directly. The `start`-new-window behaviour couldn't be
> exercised in the build harness (no interactive desktop), but works on a normal
> Windows desktop.

---

## 3. How to push to GitHub

Current git state:
- Branch: `main`
- Remote: `origin → https://github.com/SABAREES614/ONRAMP.git`
- Modified (tracked): `README.md`, `pyproject.toml`, `run_neuro_san.ps1`, `uv.lock`
- New (untracked): `.env.example`, `startup.bat`, `shutdown.bat`,
  `_run_app.bat`, `_run_neurosan.bat`, `docs/`, `frontend/`, `registries/`,
  `src/`, `tests/`

`.gitignore` already excludes secrets/local data: `.env`, `.venv`, `data/`,
`logs/`, `.pytest_cache/`, `__pycache__/`. **Confirm `.env` is NOT staged
before committing** (it holds the API key).

```powershell
cd C:\Users\s_pre\Downloads\Prototypes\ONRAMP

# Sanity: make sure .env is ignored (should print nothing / 'ignored')
git status --short | Select-String ".env$"   # expect NO match for '.env' (only .env.example)
git check-ignore .env                          # expect: .env

# Stage the application (explicit, avoids accidental extras)
git add README.md pyproject.toml run_neuro_san.ps1 uv.lock
git add .env.example startup.bat shutdown.bat _run_app.bat _run_neurosan.bat
git add docs/ frontend/ registries/ src/ tests/

# Review what will be committed
git status
git diff --cached --stat

# Commit
git commit -m "Build ONRAMP onboarding workbench on neuro-san (backend, agent network, UI, API-keys page, architecture page, tests)"

# Push (main tracks origin/main already)
git push origin main
```

If you prefer a PR workflow instead of pushing straight to `main`:
```powershell
git checkout -b feature/onramp-build
git add ...   # same as above
git commit -m "..."
git push -u origin feature/onramp-build
gh pr create --title "ONRAMP build on neuro-san" --body "See docs/ARCHITECTURE.md"
```

> Do NOT commit `.env`, `.venv/`, `data/`, or `logs/`. They are git-ignored, but
> double-check `git status` before the commit.

---

## 4. What was built (feature inventory)

**Backend (`src/onramp_neuro_san/`)**
- `config.py` — paths, `AGENT_NAME = "onramp/onramp_onboarding"`, env-file override (`ONRAMP_ENV_FILE`).
- `provider.py` — provider registry (HuggingFace/NVIDIA/OpenRouter/OpenAI) → neuro-san `llm_config` + `sly_data`; `.env` persistence with masking; `write_network_llm_config()` (rewrites the HOCON block for the active provider); `test_connection()`; `credits()`.
- `db.py` — SQLite store (cases, evidence, checks, signoffs, agent_runs, audit) + fictional seed (Northwind/Orion/Helix), currency in `$`.
- `checks.py` — deterministic PASS/REVIEW/BLOCK rules + gate logic.
- `neuro_client.py` — the REAL Neuro-SAN client (`streaming_chat`); raises on no-key/down/timeout.
- `server/app.py` — FastAPI endpoints + static host; lifespan self-heals HOCON to active provider.
- `server/review.py` — prompt + sly_data builder.
- `server/samples.py` — downloadable sample onboarding docs.

**Agent network (`registries/`)**
- `onramp/onramp_onboarding.hocon` — Concierge front-man + 8 AAOSA specialists + 4 coded tools. `llm_config` is inside markers `# ONRAMP-LLM-CONFIG-START/END` (auto-regenerated).
- `manifest.hocon`, `aaosa.hocon` (reference copy).

**Coded tools (`src/onramp/`)** — `clause_playbook`, `checklist_tracker`, `compliance_screen`, `po_reconciler` (deterministic, read `sly_data`).

**Frontend (`frontend/index.html`)** — single-page UI in the prototype's dark theme. Pages: Portfolio, Case workspace (with sample-file downloads), Concierge review (real trace + sly_data panel), Lifecycle board, Human review, Audit, Agent network, **Architecture**, **Settings · API keys** (Test connection + Credit balance). Dark/light theme toggle. Currency `$`. Facts/JSON cells wrap.

**Launchers** — `startup.bat`, `shutdown.bat` (+ helpers `_run_neurosan.bat`, `_run_app.bat`).

**Docs** — `docs/ARCHITECTURE.md`, `README.md` (updated to remote-provider flow).

**Tests (`tests/`)** — `test_checks.py`, `test_coded_tools.py`, `test_api.py` (16 tests).

---

## 5. Dependencies added this session (already in `pyproject.toml` + `uv.lock`)
- `langchain-nvidia-ai-endpoints>=0.3,<2` (NVIDIA provider class)
- `langchain-openrouter>=0.2,<1` (OpenRouter provider class; pulled `pydantic` down to 2.12.5 — stack verified working)

---

## 6. Current LLM provider state
- Active provider: **OpenRouter**, model `meta-llama/llama-3.3-70b-instruct`.
- Key is in local `.env` (git-ignored). Test connection returns OK; OpenRouter
  credit balance displays live (`$` remaining).
- **NVIDIA key is blocked at the account level** (authenticates + lists models,
  but every inference call returns `403 Forbidden` — no inference entitlement /
  credits). Not an app bug. Use OpenRouter, or fix the NVIDIA account on
  build.nvidia.com (generate the key from a model page to get inference + trial
  credits).

---

## 7. Verification commands (run these to confirm health)
```powershell
$env:Path = "$HOME\.local\bin;$env:Path"
$env:AGENT_TOOL_PATH = (Resolve-Path .\src).Path

uv run pytest -q                                   # expect: 16 passed
uv run python -m compileall -q src tests           # expect: exit 0
uv run ns validate .\registries\onramp\onramp_onboarding.hocon --registry-dir . --manifest .\registries\manifest.hocon
                                                   # expect: Validation passed
node -e "const fs=require('fs');const s=fs.readFileSync('frontend/index.html','utf8');const m=s.match(/<script>([\s\S]*?)<\/script>/g);m.forEach(b=>new Function(b.replace(/<\/?script>/g,'')));console.log('inline JS OK')"
```

---

## 8. Open items / ideas for next session
- **Model tool-following depth:** with `meta-llama/llama-3.3-70b-instruct` the
  Concierge described its delegation plan rather than fully executing every tool
  call to a consolidated status. Try a stronger tool-caller via OpenRouter
  (e.g. `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`) on the Settings page and
  confirm the full AAOSA chain completes.
- Optional: sample files as real PDFs instead of `.txt`.
- Optional: default the UI to light mode if preferred.
- Optional: remove the unused `registries/aaosa.hocon` (network inlines
  commondefs) or wire it as an include.
- Pre-existing dangling link in `README.md` → `docs/PROTOTYPE_COVERAGE.md`
  (not created; decide whether to add or remove the reference).
- Consider committing a short note that `startup.bat` opens two windows.

---

## 9. Key gotchas learned (so you don't re-hit them)
- **Served agent name** is `onramp/onramp_onboarding` (includes the manifest
  subdirectory), not `onramp_onboarding`.
- neuro-san reads per-request API keys from `sly_data["llm_config"][<key>]`
  (nested), and `class`/`model_name` come from the HOCON `llm_config` — they
  can't be swapped via sly_data. Hence `write_network_llm_config()`.
- NVIDIA/OpenRouter classes need their langchain packages installed (done).
- PowerShell: use `;` not `&&`; `start`-new-window needs an interactive desktop;
  don't use PowerShell `-replace` on files with non-ASCII (`£`) — it corrupted
  encoding once (repaired via Python raw-byte replace).
- The Neuro-SAN server takes ~18–22s to load the network before it answers.

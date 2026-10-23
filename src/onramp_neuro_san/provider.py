"""LLM provider configuration for ONRAMP.

ONRAMP uses only remote, OpenAI-compatible providers (no local Ollama). Each
provider maps to a neuro-san LLM *class* and a set of environment-variable /
``llm_config`` keys that neuro-san resolves via ``get_value_or_env``.

Supported here:

* ``huggingface`` - HuggingFace Inference Router, OpenAI-compatible. Uses the
  neuro-san ``openai`` class with a custom ``openai_api_base`` pointing at
  ``https://router.huggingface.co/v1``.
* ``nvidia``      - NVIDIA NIM / integrate API. Uses the native ``nvidia`` class.
* ``openrouter``  - OpenRouter. Uses the native ``openrouter`` class.
* ``openai``      - OpenAI (or any OpenAI-compatible endpoint via base url).

The API-keys settings page writes the selected provider, model name and the
provider API keys into the project ``.env``. Keys are never returned to the UI
in clear text - only a masked preview and a "configured" flag.

Because the neuro-san server reads these environment variables at request time
(through ``get_value_or_env``), ONRAMP also injects the active provider's key
into the per-request ``sly_data`` so the key travels on the private channel and
never appears in the chat/prompt stream. This is the real, documented
mechanism - there are no mock or dummy LLM calls anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ENV_FILE, load_env
from .config import REGISTRIES_DIR


@dataclass(frozen=True)
class ProviderSpec:
    """Describes how a provider maps onto neuro-san's llm_config."""

    key: str                      # internal id, e.g. "huggingface"
    label: str                    # human label for the UI
    llm_class: str                # neuro-san LLM class name
    api_key_env: str              # env var the neuro-san class reads for the key
    api_key_cfg: str              # llm_config/sly_data key for the api key
    base_url_env: str | None      # env var for a custom base url (if any)
    base_url_cfg: str | None      # llm_config key for the base url (if any)
    default_base_url: str | None  # sensible default base url
    default_model: str            # a reasonable default model id
    model_help: str               # guidance shown in the UI
    key_help: str                 # where to get a key


PROVIDERS: dict[str, ProviderSpec] = {
    "huggingface": ProviderSpec(
        key="huggingface",
        label="Hugging Face (Inference Router)",
        llm_class="openai",
        api_key_env="OPENAI_API_KEY",
        api_key_cfg="openai_api_key",
        base_url_env="OPENAI_API_BASE",
        base_url_cfg="openai_api_base",
        default_base_url="https://router.huggingface.co/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct",
        model_help=(
            "Any model id served by the HuggingFace router, e.g. "
            "'meta-llama/Llama-3.3-70B-Instruct' or "
            "'Qwen/Qwen2.5-72B-Instruct'. Must support tool calling to act as "
            "the Concierge front-man."
        ),
        key_help="Create a token at https://huggingface.co/settings/tokens",
    ),
    "nvidia": ProviderSpec(
        key="nvidia",
        label="NVIDIA (build.nvidia.com / NIM)",
        llm_class="nvidia",
        api_key_env="NVIDIA_API_KEY",
        api_key_cfg="nvidia_api_key",
        base_url_env="NVIDIA_BASE_URL",
        base_url_cfg="nvidia_base_url",
        default_base_url="https://integrate.api.nvidia.com/v1",
        default_model="nvidia/llama-3.3-nemotron-super-49b-v1.5",
        model_help=(
            "A current NVIDIA-hosted model id that supports tool calling, e.g. "
            "'nvidia/llama-3.3-nemotron-super-49b-v1.5', "
            "'nvidia/llama-3.1-nemotron-ultra-253b-v1', or "
            "'nvidia/nemotron-3-nano-30b-a3b'. Avoid vision ('-vl-') and "
            "end-of-life models. Browse ids at https://build.nvidia.com/models."
        ),
        key_help="Create a key at https://build.nvidia.com (API Keys)",
    ),
    "openrouter": ProviderSpec(
        key="openrouter",
        label="OpenRouter (Free API Key)",
        llm_class="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        api_key_cfg="openrouter_api_key",
        base_url_env="OPENROUTER_API_BASE",
        base_url_cfg="openrouter_api_base",
        default_base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/auto",
        model_help=(
            "An OpenRouter model id, e.g. 'anthropic/claude-3.5-sonnet', "
            "'openai/gpt-4o-mini', or the meta-routers 'openrouter/auto' / "
            "'openrouter/free'."
        ),
        key_help="Create a key at https://openrouter.ai/keys",
    ),
    "openai": ProviderSpec(
        key="openai",
        label="OpenAI (or OpenAI-compatible endpoint)",
        llm_class="openai",
        api_key_env="OPENAI_API_KEY",
        api_key_cfg="openai_api_key",
        base_url_env="OPENAI_API_BASE",
        base_url_cfg="openai_api_base",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        model_help="An OpenAI model id, e.g. 'gpt-4o-mini' or 'gpt-4o'.",
        key_help="Create a key at https://platform.openai.com/api-keys",
    ),
}

DEFAULT_PROVIDER = "huggingface"

# Env var names ONRAMP itself owns (selection, not secrets).
ENV_PROVIDER = "ONRAMP_PROVIDER"
ENV_MODEL = "ONRAMP_MODEL"


@dataclass
class ActiveConfig:
    """The currently-selected provider/model and whether a key is present."""

    provider: str
    model: str
    base_url: str
    has_key: bool
    masked_key: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def spec(self) -> ProviderSpec:
        return PROVIDERS[self.provider]


def mask_key(value: str | None) -> str:
    """Return a masked preview of a secret, never the full value."""
    if not value:
        return ""
    value = value.strip()
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 6}{value[-4:]}"


def _read_env_file() -> dict[str, str]:
    """Parse the project .env into a dict (empty if missing)."""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, val = line.partition("=")
        result[name.strip()] = val.strip()
    return result


def _write_env_file(values: dict[str, str]) -> None:
    """Persist key/value pairs to the project .env, preserving other keys."""
    existing = _read_env_file()
    existing.update({k: v for k, v in values.items() if v is not None})
    # Drop empty values so we don't leave blank assignments around.
    lines = ["# ONRAMP local environment - git-ignored. Do not commit secrets.",
             "# Managed by the Settings / API keys page; safe to edit by hand."]
    for name in sorted(existing):
        val = existing[name]
        if val == "":
            continue
        lines.append(f"{name}={val}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def active_provider() -> str:
    load_env()
    prov = os.environ.get(ENV_PROVIDER, "").strip() or _read_env_file().get(ENV_PROVIDER, "")
    prov = prov.strip() or DEFAULT_PROVIDER
    return prov if prov in PROVIDERS else DEFAULT_PROVIDER


def active_config() -> ActiveConfig:
    """Resolve the active provider/model and key presence from env/.env."""
    load_env()
    env = _read_env_file()
    prov = active_provider()
    spec = PROVIDERS[prov]

    def _get(name: str) -> str:
        return (os.environ.get(name) or env.get(name) or "").strip()

    model = _get(ENV_MODEL) or spec.default_model
    base_url = _get(spec.base_url_env) if spec.base_url_env else ""
    base_url = base_url or (spec.default_base_url or "")
    key = _get(spec.api_key_env)

    return ActiveConfig(
        provider=prov,
        model=model,
        base_url=base_url,
        has_key=bool(key),
        masked_key=mask_key(key),
    )


def key_status() -> dict[str, dict[str, Any]]:
    """Return per-provider key presence + masked preview for the UI."""
    load_env()
    env = _read_env_file()
    status: dict[str, dict[str, Any]] = {}
    for key, spec in PROVIDERS.items():
        raw = (os.environ.get(spec.api_key_env) or env.get(spec.api_key_env) or "").strip()
        status[key] = {
            "label": spec.label,
            "llm_class": spec.llm_class,
            "api_key_env": spec.api_key_env,
            "has_key": bool(raw),
            "masked_key": mask_key(raw),
            "base_url_env": spec.base_url_env,
            "default_base_url": spec.default_base_url,
            "default_model": spec.default_model,
            "model_help": spec.model_help,
            "key_help": spec.key_help,
        }
    return status


def save_settings(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ActiveConfig:
    """Persist provider selection, model, optional key and base url to .env.

    ``api_key`` is only written when a non-empty value is supplied, so that
    saving the form without re-typing the key keeps the existing one.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'")
    spec = PROVIDERS[provider]

    to_write: dict[str, str] = {ENV_PROVIDER: provider}
    if model:
        to_write[ENV_MODEL] = model.strip()
    if api_key and api_key.strip() and not _is_masked(api_key):
        to_write[spec.api_key_env] = api_key.strip()
    if base_url is not None and spec.base_url_env:
        bu = base_url.strip() or (spec.default_base_url or "")
        if bu:
            to_write[spec.base_url_env] = bu

    _write_env_file(to_write)
    # Reflect into the live process environment so the next call sees it.
    for name, val in to_write.items():
        os.environ[name] = val
    # Rewrite the network HOCON so the Neuro-SAN server uses the chosen provider's
    # class/model (the server auto-reloads the manifest every few seconds).
    try:
        write_network_llm_config()
    except OSError:
        pass
    return active_config()


NETWORK_HOCON = REGISTRIES_DIR / "onramp" / "onramp_onboarding.hocon"
_LLM_START = "# ONRAMP-LLM-CONFIG-START"
_LLM_END = "# ONRAMP-LLM-CONFIG-END"


def write_network_llm_config() -> None:
    """Regenerate the marked llm_config block in the network HOCON.

    class/model_name cannot be overridden per request via sly_data (neuro-san
    takes them from the network's llm_config), so when the user changes the
    provider/model we rewrite the block. The api key stays as the literal
    "sly_data" placeholder and is supplied per request on the private channel.
    """
    if not NETWORK_HOCON.exists():
        return
    cfg = active_config()
    spec = cfg.spec

    indent = "    "
    lines = [
        _LLM_START,
        f'{indent}"llm_config": {{',
        f'{indent}    "class": "{spec.llm_class}",',
    ]
    # Build the inner lines, then join so only the last one has no trailing comma.
    inner = [f'"model_name": "{cfg.model}"']
    if spec.base_url_cfg and cfg.base_url:
        inner.append(f'"{spec.base_url_cfg}": "{cfg.base_url}"')
    # NOTE: the API key is intentionally NOT written here. The provider class
    # resolves it from the server environment variable (e.g. OPENROUTER_API_KEY),
    # which the neuro-san server loads from the project .env on startup. This
    # lets BOTH the ONRAMP app and the nsflow chat UI use the same credentials.
    # (ONRAMP also passes the key via sly_data, which takes precedence when set.)
    for i, line in enumerate(inner):
        comma = "," if i < len(inner) - 1 else ""
        lines.append(f"{indent}    {line}{comma}")
    lines.append(f"{indent}}},")
    lines.append(f"{indent}{_LLM_END}")
    new_block = "\n".join(lines)

    text = NETWORK_HOCON.read_text(encoding="utf-8")
    start = text.find(_LLM_START)
    end = text.find(_LLM_END)
    if start == -1 or end == -1:
        return
    # Replace from the start marker through the end marker (inclusive).
    end_full = end + len(_LLM_END)
    # Preserve the leading indentation on the start-marker line.
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[:line_start]
    suffix = text[end_full:]
    NETWORK_HOCON.write_text(prefix + new_block + suffix, encoding="utf-8")


def _is_masked(value: str) -> bool:
    """Treat a value containing the mask bullet as 'unchanged'."""
    return "•" in value


def build_llm_config() -> dict[str, Any]:
    """Build the neuro-san ``llm_config`` overrides for the active provider.

    Returned dict is merged into the network's llm_config at request time (or
    used to validate configuration). It intentionally does NOT include the API
    key - the key is delivered via sly_data (private channel).
    """
    cfg = active_config()
    spec = cfg.spec
    out: dict[str, Any] = {
        "class": spec.llm_class,
        "model_name": cfg.model,
    }
    if spec.base_url_cfg and cfg.base_url:
        out[spec.base_url_cfg] = cfg.base_url
    return out


def build_sly_data() -> dict[str, Any]:
    """Build the per-request sly_data carrying the API key off the prompt path.

    neuro-san fills any llm_config value set to the literal string ``"sly_data"``
    from ``sly_data["llm_config"][<key>]`` (see DefaultLlmFactory
    .replace_any_required_api_keys). So the key MUST be nested under an inner
    ``llm_config`` dict, keyed by the provider's config key (e.g.
    ``nvidia_api_key``, ``openai_api_key``). Returns an empty dict if no key is
    configured (caller then surfaces a configuration error rather than making a
    dummy call).
    """
    load_env()
    env = _read_env_file()
    cfg = active_config()
    spec = cfg.spec
    raw = (os.environ.get(spec.api_key_env) or env.get(spec.api_key_env) or "").strip()
    if not raw:
        return {}
    inner: dict[str, Any] = {spec.api_key_cfg: raw}
    if spec.base_url_cfg and cfg.base_url:
        inner[spec.base_url_cfg] = cfg.base_url
    return {"llm_config": inner}


def provider_options() -> list[dict[str, str]]:
    """Provider list for the UI select control."""
    return [{"key": k, "label": v.label} for k, v in PROVIDERS.items()]


def _raw_key() -> str:
    """Return the active provider's API key (raw), or '' if unset."""
    load_env()
    env = _read_env_file()
    spec = PROVIDERS[active_provider()]
    return (os.environ.get(spec.api_key_env) or env.get(spec.api_key_env) or "").strip()


def test_connection() -> dict[str, Any]:
    """Make a real minimal chat completion against the active provider/model.

    Returns a dict with ``ok`` plus latency and a short message or error.
    Does not raise. Never returns the key.
    """
    import time

    import httpx

    cfg = active_config()
    spec = cfg.spec
    key = _raw_key()
    if not key:
        return {"ok": False, "provider": cfg.provider, "model": cfg.model,
                "error": f"No API key set for {spec.label}."}

    base = cfg.base_url or (spec.default_base_url or "")
    url = base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "max_tokens": 8,
    }
    started = time.perf_counter()
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    except Exception as exc:  # pragma: no cover - network
        return {"ok": False, "provider": cfg.provider, "model": cfg.model,
                "error": f"Could not reach {base}: {exc}"}
    latency_ms = int((time.perf_counter() - started) * 1000)

    if resp.status_code == 200:
        text = ""
        try:
            text = resp.json()["choices"][0]["message"]["content"][:60]
        except (KeyError, IndexError, ValueError):
            pass
        return {"ok": True, "provider": cfg.provider, "model": cfg.model,
                "latency_ms": latency_ms, "sample": text or "(ok)"}

    detail = resp.text[:200]
    hint = ""
    if resp.status_code in (401, 403):
        hint = " — the key is rejected for inference. Check it is valid and has access/credits for this model."
    elif resp.status_code == 404:
        hint = " — model id not found for this provider. Check the model name."
    elif resp.status_code == 410:
        hint = " — this model has reached end of life. Pick a current model."
    return {"ok": False, "provider": cfg.provider, "model": cfg.model,
            "status": resp.status_code, "latency_ms": latency_ms,
            "error": f"HTTP {resp.status_code}: {detail}{hint}"}


def credits() -> dict[str, Any]:
    """Return credit/usage info for the active provider where exposed.

    OpenRouter exposes GET /key (usage, limit, remaining). Other providers do
    not offer a standard credit endpoint, so we return a 'not exposed'
    placeholder. Does not raise; never returns the key.
    """
    import httpx

    cfg = active_config()
    key = _raw_key()
    if not key:
        return {"available": False, "reason": "No API key set."}

    if cfg.provider == "openrouter":
        base = cfg.base_url or "https://openrouter.ai/api/v1"
        try:
            resp = httpx.get(base.rstrip("/") + "/key",
                             headers={"Authorization": f"Bearer {key}"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                usage = data.get("usage")
                limit = data.get("limit")  # None => unlimited
                remaining = None
                if isinstance(limit, (int, float)) and isinstance(usage, (int, float)):
                    remaining = round(limit - usage, 4)
                return {
                    "available": True,
                    "provider": "openrouter",
                    "currency": "$",
                    "usage": usage,
                    "limit": limit,
                    "remaining": remaining,
                    "is_free_tier": data.get("is_free_tier"),
                }
            return {"available": False,
                    "reason": f"OpenRouter /key returned HTTP {resp.status_code}."}
        except Exception as exc:  # pragma: no cover - network
            return {"available": False, "reason": f"Could not query OpenRouter: {exc}"}

    return {"available": False,
            "reason": f"{cfg.spec.label} does not expose a standard credit-balance API. "
                      "Check your balance on the provider's dashboard."}

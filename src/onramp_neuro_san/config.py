"""Central configuration for ONRAMP.

Loads settings from environment / ``.env`` and exposes typed accessors for the
rest of the app. Secrets (LLM API keys) are read here but never logged or
returned to the UI in clear text.

No local model runtime is used. ONRAMP talks to remote, OpenAI-compatible
providers (HuggingFace router, NVIDIA, OpenRouter, OpenAI) through the
neuro-san ``llm_config`` mechanism. See ``provider.py`` for the mapping to
neuro-san LLM classes and environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project layout ------------------------------------------------------------
# src/onramp_neuro_san/config.py -> parents[2] is the project root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
REGISTRIES_DIR: Path = PROJECT_ROOT / "registries"
MANIFEST_FILE: Path = REGISTRIES_DIR / "manifest.hocon"
CODED_TOOLS_DIR: Path = PROJECT_ROOT / "src"  # AGENT_TOOL_PATH root
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"

DATA_DIR: Path = PROJECT_ROOT / "data"
UPLOADS_DIR: Path = DATA_DIR / "uploads"
DB_PATH: Path = Path(os.environ.get("ONRAMP_DB", str(DATA_DIR / "onramp.db")))

# The .env file lives at the project root and is git-ignored.
# Overridable via ONRAMP_ENV_FILE (used by tests to avoid touching the real file).
ENV_FILE: Path = Path(os.environ.get("ONRAMP_ENV_FILE", str(PROJECT_ROOT / ".env")))

# The agent network served by neuro-san. The served name includes the manifest
# subdirectory prefix (manifest key 'onramp/onramp_onboarding.hocon').
AGENT_NAME: str = "onramp/onramp_onboarding"

# Upload constraints (per README): PDF/DOC/DOCX/TXT up to 15 MB.
MAX_UPLOAD_BYTES: int = 15 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = (".pdf", ".doc", ".docx", ".txt")


def load_env() -> None:
    """Load the project ``.env`` into ``os.environ`` (idempotent)."""
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)


def ensure_dirs() -> None:
    """Create the local data directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class NeuroSanSettings:
    """Connection settings for the running neuro-san server."""

    host: str
    http_port: int
    connect_timeout_s: float
    streaming_timeout_s: float

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.http_port}"


def neuro_san_settings() -> NeuroSanSettings:
    """Read neuro-san connection settings from the environment."""
    load_env()
    return NeuroSanSettings(
        host=os.environ.get("NEURO_SAN_HOST", "127.0.0.1"),
        http_port=int(os.environ.get("NEURO_SAN_HTTP_PORT", "8080")),
        connect_timeout_s=float(os.environ.get("NEURO_SAN_CONNECT_TIMEOUT", "20")),
        streaming_timeout_s=float(os.environ.get("NEURO_SAN_STREAM_TIMEOUT", "180")),
    )

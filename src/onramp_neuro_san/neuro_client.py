"""Real Neuro-SAN client for ONRAMP.

Connects to a running neuro-san server over HTTP and drives the
``onramp_onboarding`` agent network. This is the ONLY path to an LLM result -
there are no mock, dummy or simulated responses anywhere. If the network is not
running, the provider key is missing, or the call errors/times out, this raises
and the caller records the failure and blocks approval.

Ground truth (verified against the installed neuro-san 0.7.7):
* AgentSessionFactory().create_session("http", agent_name=..., hostname=...,
  port=..., connect_timeout_in_seconds=...)
* session.streaming_chat({"user_message": {"type": ChatMessageType.HUMAN,
  "text": ...}, "sly_data": {...}}) yields ChatResponse dicts each with a
  "response" ChatMessage ({"type", "text", "structure", ...}).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.message.types.chat_message_type import ChatMessageType

from . import provider
from .config import AGENT_NAME, neuro_san_settings


class NeuroSanError(RuntimeError):
    """Raised when the real Neuro-SAN call cannot complete."""


@dataclass
class RunResult:
    """Outcome of a real network run."""

    status: str                                  # "success"
    answer: str
    structure: dict[str, Any] | None
    trace: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    duration_ms: int = 0


def _message_text(msg: dict[str, Any]) -> str:
    return (msg or {}).get("text", "") or ""


def run_network(prompt: str, sly_data: dict[str, Any] | None = None,
                agent_name: str = AGENT_NAME) -> RunResult:
    """Drive the agent network once and return the final answer + full trace.

    Raises ``NeuroSanError`` on any failure (no key, server down, timeout,
    empty stream). The caller is responsible for recording the failure.
    """
    active = provider.active_config()
    if not active.has_key:
        raise NeuroSanError(
            f"No API key configured for provider '{active.provider}'. "
            "Set it on the Settings / API keys page before running a review."
        )

    settings = neuro_san_settings()
    merged_sly: dict[str, Any] = dict(provider.build_sly_data())
    if sly_data:
        merged_sly.update(sly_data)

    try:
        factory = AgentSessionFactory()
        session = factory.create_session(
            "http",
            agent_name=agent_name,
            hostname=settings.host,
            port=settings.http_port,
            connect_timeout_in_seconds=settings.connect_timeout_s,
        )
    except Exception as exc:  # pragma: no cover - connection setup
        raise NeuroSanError(f"Could not create a session to the Neuro-SAN "
                            f"server at {settings.base_url}: {exc}") from exc

    request = {
        "user_message": {
            "type": int(ChatMessageType.HUMAN),
            "text": prompt,
        },
        "sly_data": merged_sly,
        # Ask the server for the full agent conversation (all specialist turns
        # and the final AI answer), not just framework/progress messages.
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
    }

    trace: list[dict[str, Any]] = []
    final_answer = ""
    final_structure: dict[str, Any] | None = None
    import time
    _t0 = time.perf_counter()

    try:
        for chat_response in session.streaming_chat(request):
            response = (chat_response or {}).get("response")
            if not response:
                continue
            msg_type = response.get("type")
            text = _message_text(response)
            origin = response.get("origin")
            origin_name = ""
            if isinstance(origin, list) and origin:
                origin_name = origin[-1].get("tool", "") if isinstance(origin[-1], dict) else ""
            # Capture a redacted view of each message for the raw trace panel.
            trace.append({
                "type": msg_type,
                "type_name": _type_name(msg_type),
                "origin": origin_name,
                "text": text,
                "structure": response.get("structure"),
            })
            # The front-man's AI message carries the final answer.
            if msg_type in (int(ChatMessageType.AI), int(ChatMessageType.AGENT)) and text:
                final_answer = text
                if response.get("structure"):
                    final_structure = response.get("structure")
    except NeuroSanError:
        raise
    except Exception as exc:
        raise NeuroSanError(
            f"Neuro-SAN streaming_chat failed against {settings.base_url} "
            f"for agent '{agent_name}': {exc}"
        ) from exc
    finally:
        try:
            session.close()
        except Exception:  # pragma: no cover
            pass

    if not trace:
        raise NeuroSanError(
            "The Neuro-SAN network returned no messages. Is the server running "
            f"at {settings.base_url} and the '{agent_name}' network served?"
        )
    if not final_answer:
        # Fall back to the last text message in the trace.
        for item in reversed(trace):
            if item.get("text"):
                final_answer = item["text"]
                break

    return RunResult(
        status="success",
        answer=final_answer,
        structure=final_structure,
        trace=trace,
        provider=active.provider,
        model=active.model,
        duration_ms=int((time.perf_counter() - _t0) * 1000),
    )


def _type_name(msg_type: Any) -> str:
    try:
        return ChatMessageType(int(msg_type)).name
    except (ValueError, TypeError):
        return str(msg_type)


def ping() -> dict[str, Any]:
    """Lightweight reachability probe of the Neuro-SAN server.

    Uses the ``function`` endpoint (cheap, no LLM) to confirm the agent is
    served. Returns a dict with ``reachable`` and any error message. Does not
    raise.
    """
    settings = neuro_san_settings()
    try:
        factory = AgentSessionFactory()
        session = factory.create_session(
            "http",
            agent_name=AGENT_NAME,
            hostname=settings.host,
            port=settings.http_port,
            connect_timeout_in_seconds=min(settings.connect_timeout_s, 5),
        )
        result = session.function({})
        session.close()
        return {"reachable": True, "base_url": settings.base_url,
                "function": result.get("function", {})}
    except Exception as exc:
        return {"reachable": False, "base_url": settings.base_url, "error": str(exc)}

"""trace_id helpers — align with Hermes session when available."""

from __future__ import annotations

from uuid import uuid4


def new_trace_id() -> str:
    return str(uuid4())


def trace_from_session(session_id: str) -> str:
    """Map shell session id to trace_id (v1: prefix; v2: lookup table)."""
    sid = session_id.strip()
    if sid.startswith("trace:"):
        return sid.removeprefix("trace:")
    return f"hermes-{sid}"

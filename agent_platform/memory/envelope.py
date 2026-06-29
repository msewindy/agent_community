"""MemVerse wire format — encodes product schema into a single query string."""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.memory.contracts import MemoryCategory, MemoryKind

ENVELOPE_VERSION = "v1"
ENVELOPE_PREFIX = f"[agent_memory_{ENVELOPE_VERSION}]"

_ENVELOPE_RE = re.compile(
    r"^\[agent_memory_v1\]\s+"
    r"device_id=(?P<device_id>\S+)\s+"
    r"category=(?P<category>\S+)\s+"
    r"kind=(?P<kind>\S+)\s+"
    r"record_id=(?P<record_id>\S+)\s+"
    r"content=(?P<content>.+)$",
    re.DOTALL,
)


def encode_envelope(
    *,
    device_id: str,
    category: MemoryCategory,
    kind: MemoryKind,
    record_id: str,
    content: str,
) -> str:
    """Pack device_id / category / kind / record_id into MemVerse ``query`` form field."""
    return (
        f"{ENVELOPE_PREFIX} "
        f"device_id={device_id} "
        f"category={category.value} "
        f"kind={kind.value} "
        f"record_id={record_id} "
        f"content={content}"
    )


def decode_envelope(text: str) -> Optional[dict[str, str]]:
    m = _ENVELOPE_RE.match(text.strip())
    if not m:
        return None
    return m.groupdict()


def parse_category(value: str) -> Optional[MemoryCategory]:
    try:
        return MemoryCategory(value)
    except ValueError:
        return None


def parse_kind(value: str) -> Optional[MemoryKind]:
    try:
        return MemoryKind(value)
    except ValueError:
        return None

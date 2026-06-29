"""M2 D2 — MemVerse envelope encode/decode tests."""

from __future__ import annotations

from agent_platform.memory.contracts import MemoryCategory, MemoryKind
from agent_platform.memory.envelope import (
    ENVELOPE_PREFIX,
    decode_envelope,
    encode_envelope,
    parse_category,
    parse_kind,
)


def test_encode_decode_round_trip():
    text = encode_envelope(
        device_id="reachy-desktop-01",
        category=MemoryCategory.preference,
        kind=MemoryKind.preference,
        record_id="rec-001",
        content="用户偏好：回复尽量简短",
    )
    assert text.startswith(ENVELOPE_PREFIX)
    parsed = decode_envelope(text)
    assert parsed is not None
    assert parsed["device_id"] == "reachy-desktop-01"
    assert parsed["category"] == "preference"
    assert parsed["kind"] == "preference"
    assert parsed["record_id"] == "rec-001"
    assert parsed["content"] == "用户偏好：回复尽量简短"


def test_decode_multiline_content():
    content = "第一行\n第二行"
    wire = encode_envelope(
        device_id="d1",
        category=MemoryCategory.other,
        kind=MemoryKind.note,
        record_id="r1",
        content=content,
    )
    parsed = decode_envelope(wire)
    assert parsed is not None
    assert parsed["content"] == content


def test_decode_rejects_plain_text():
    assert decode_envelope("plain memory without envelope") is None


def test_parse_category_and_kind():
    assert parse_category("preference") == MemoryCategory.preference
    assert parse_category("invalid") is None
    assert parse_kind("episode") == MemoryKind.episode

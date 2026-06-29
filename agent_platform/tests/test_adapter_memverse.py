"""M2 D4 — MemVerseAdapter unit (mocked HTTP) + optional integration."""

from __future__ import annotations

import json

import httpx
import pytest

from agent_platform.memory.adapters.memverse import MemVerseAdapter, _hits_from_query_response, _is_error_text
from agent_platform.memory.contracts import (
    MemoryCategory,
    MemoryKind,
    MemorySearchRequest,
    MemoryWriteRequest,
)
from agent_platform.memory.envelope import encode_envelope


def test_is_error_text_detects_failures() -> None:
    assert _is_error_text("⚠️ RAG retrieval failed: Error 400")
    assert not _is_error_text("用户偏好：简短回复")


def test_hits_from_query_uses_final_answer_not_error() -> None:
    raw = {
        "status": "ok",
        "final_answer": "根据记忆，你喜欢简短回复。",
        "rag_memory": "⚠️ RAG retrieval failed: bad model",
    }
    hits = _hits_from_query_response(raw, device_id=None, category=None)
    assert len(hits) == 1
    assert "简短" in hits[0].content


def test_memverse_adapter_write_mocked(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/insert",
        json={"status": "ok", "entry": {"id": "e1"}},
    )
    ad = MemVerseAdapter("http://127.0.0.1:8000", timeout_s=5)
    rec = ad.write(
        MemoryWriteRequest(
            content="偏好简短",
            device_id="dev-1",
            category=MemoryCategory.preference,
            kind=MemoryKind.preference,
        )
    )
    assert rec.device_id == "dev-1"
    assert rec.metadata.get("memverse_entry") == {"id": "e1"}


def test_memverse_adapter_search_mocked(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/query",
        json={
            "status": "ok",
            "final_answer": "你偏好简短回复。",
            "rag_memory": None,
        },
    )
    ad = MemVerseAdapter("http://127.0.0.1:8000", timeout_s=5)
    res = ad.search(MemorySearchRequest(query="简短", device_id="dev-1"))
    assert len(res.hits) == 1
    assert "简短" in res.hits[0].content


@pytest.mark.integration
def test_memverse_e2e_write_search() -> None:
    """Requires MemVerse Docker on :8000 with OPENAI_MODEL=deepseek-chat."""
    ad = MemVerseAdapter("http://127.0.0.1:8000", timeout_s=180)
    if not ad.ping():
        pytest.skip("MemVerse not reachable on :8000")

    device = "m2-d4-test"
    marker = "M2D4_UNIQUE_PREFERENCE_SHORT_REPLIES"
    rec = ad.write(
        MemoryWriteRequest(
            content=f"{marker}：用户偏好简短回复",
            device_id=device,
            category=MemoryCategory.preference,
            kind=MemoryKind.preference,
        )
    )
    assert rec.record_id

    res = ad.search(MemorySearchRequest(query=marker, device_id=device, limit=5))
    assert res.raw is not None
    assert res.raw.get("status") == "ok"

    fa = (res.raw.get("final_answer") or "") if res.raw else ""
    rag = (res.raw.get("rag_memory") or "") if res.raw else ""
    has_signal = (
        len(res.hits) > 0
        or (fa and not _is_error_text(fa))
        or (rag and not _is_error_text(rag))
    )
    assert has_signal, f"no usable hits; final_answer={fa[:200]!r} rag={rag[:200]!r}"

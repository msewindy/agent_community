"""Unit tests for DashScope ASR text extraction."""

from __future__ import annotations

from agent_platform.voice.dashscope_asr import _sentence_text


def test_sentence_text_from_dict() -> None:
    assert _sentence_text({"text": "你好"}) == "你好"


def test_sentence_text_from_list() -> None:
    sent = [{"text": "Hello "}, {"text": "world"}]
    assert _sentence_text(sent) == "Hello world"

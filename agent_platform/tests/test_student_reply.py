"""Tests for student-facing reply sanitization."""

from __future__ import annotations

from agent_platform.learning.student_reply import sanitize_student_reply


def test_strip_alignment_preamble_before_hrule() -> None:
    raw = """当前学科和单元已经对齐了，就是 **语文 · 美丽的校园（部编版三年级上册）**，不用切换啦！

---

好的，盈熙！贾维斯来啦。

三年级语文第一单元叫 **《美丽的校园》**。"""
    clean = sanitize_student_reply(raw)
    assert "已经对齐" not in clean
    assert "不用切换" not in clean
    assert "盈熙" in clean
    assert "《美丽的校园》" in clean


def test_preserves_normal_teaching_without_framework() -> None:
    text = "好的，盈熙！第一单元《美丽的校园》有两篇课文……"
    assert sanitize_student_reply(text) == text


def test_strip_leading_framework_paragraph() -> None:
    raw = (
        "already_current 为 true，单元未变，不用切换。\n\n"
        "我们来学《大青树下的小学》吧。"
    )
    clean = sanitize_student_reply(raw)
    assert "already_current" not in clean
    assert "大青树下的小学" in clean


def test_empty_after_only_framework() -> None:
    assert sanitize_student_reply("当前学科和单元已经对齐了，不用切换啦！") == ""

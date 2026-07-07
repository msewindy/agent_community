"""Prompt rules for learning focus."""

from __future__ import annotations

from agent_platform.learning.prompts import (
    LEARNING_FOCUS_RULES,
    format_pre_llm_context,
)


def test_teach_intent_includes_learning_focus_rules() -> None:
    block = format_pre_llm_context(
        prompt_block="## 学生学习情境\n- 学科/单元：数学 · 两步四则运算（math-g3-u01）",
        gaps=[],
        user_message="我想学英语第一单元",
    )
    assert LEARNING_FOCUS_RULES.splitlines()[0] in block
    assert "learning_focus_set" in block
    assert "explain_kp" in block
    assert "绝对禁止泄露框架" in block


def test_learning_focus_rules_mention_no_hello() -> None:
    assert "Hello" in LEARNING_FOCUS_RULES or "通用" in LEARNING_FOCUS_RULES

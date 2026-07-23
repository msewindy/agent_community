"""Prompt rules for learning focus."""

from __future__ import annotations

from agent_platform.learning.prompts import (
    INTENT_ANSWER_FOLLOWUP_RULES,
    INTENT_PRACTICE_RULES,
    LEARNING_FOCUS_RULES,
    detect_answer_followup_intent,
    detect_practice_intent,
    format_pre_llm_context,
    practice_bank_status_block,
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


def test_practice_intent_forbids_oral_closed_loop() -> None:
    assert "禁止" in INTENT_PRACTICE_RULES
    assert "attempt_submit" in INTENT_PRACTICE_RULES
    assert "empty_bank" in INTENT_PRACTICE_RULES or "count=0" in INTENT_PRACTICE_RULES
    block = format_pre_llm_context(
        prompt_block="## 学生学习情境\n- 学科/单元：数学 · 两步四则运算（math-g3-u01）",
        gaps=[],
        user_message="出几道题考考我",
    )
    assert INTENT_PRACTICE_RULES.splitlines()[0] in block
    assert detect_practice_intent("出几道题考考我")


def test_answer_followup_injects_submit_rules() -> None:
    assert "attempt_submit" in INTENT_ANSWER_FOLLOWUP_RULES
    assert detect_answer_followup_intent("答案是18")
    block = format_pre_llm_context(
        prompt_block="## 学生学习情境\n- 学科/单元：数学 · 两步四则运算（math-g3-u01）",
        gaps=[],
        user_message="答案是18",
    )
    assert INTENT_ANSWER_FOLLOWUP_RULES.splitlines()[0] in block


def test_practice_bank_status_empty() -> None:
    text = practice_bank_status_block(unit_id="chinese-g3-u01", question_count=0)
    assert "0" in text
    assert "禁止自编题" in text

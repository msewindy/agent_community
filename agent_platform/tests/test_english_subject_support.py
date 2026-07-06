"""English subject support — taxonomy, onboarding, prompts, grader."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.grader import Grader
from agent_platform.learning.contracts import AnswerType, Question
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.prompts import build_student_system_prompt, format_pre_llm_context
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.subject_pilot import pilot_unit_id
from agent_platform.learning.taxonomy import TaxonomyService


def test_english_error_codes_in_taxonomy() -> None:
    tax = TaxonomyService()
    for code in ("SPELLING_ERROR", "GRAMMAR_ERROR", "VOCAB_GAP", "EN_READING_ERROR"):
        entry = tax.lookup(code)
        assert entry.knowledge_point_id.startswith("kp-en-")


def test_pilot_unit_id_english() -> None:
    units = {"math": "m1", "chinese": "c1", "english": "e1"}
    assert pilot_unit_id(units, "英语") == "e1"
    assert pilot_unit_id(units, "数学") == "m1"
    assert pilot_unit_id(units, "语文") == "c1"


def test_english_unit_in_catalog() -> None:
    cat = KpCatalogService()
    unit = cat.get_unit("english-g3-starter")
    assert unit.subject == "英语"
    assert len(unit.knowledge_points) >= 4
    assert "英语" in cat.list_subjects()


def test_onboard_english_primary_subject(tmp_path: Path) -> None:
    data = tmp_path / "student_data"
    catalog = KpCatalogService()
    ctx = StudentContextService(data_root=data)
    onboarding = OnboardingService(data_root=data, context_svc=ctx, catalog=catalog)
    sid = "stu-en"
    profile = onboarding.onboard(
        sid,
        grade="三年级",
        grade_level=3,
        primary_subject="英语",
    )
    assert profile.active_unit_id == "english-g3-starter"
    assert profile.primary_subject == "英语"
    snap = ctx.get(sid)
    assert snap.curriculum.subject == "英语"


def test_prompts_use_current_subject() -> None:
    block = "## 学生学习情境\n- 学科/单元：英语 · 入门单元（english-g3-starter）"
    sys_prompt = build_student_system_prompt("英语")
    assert "词汇" in sys_prompt or "拼写" in sys_prompt
    ctx = format_pre_llm_context(prompt_block=block, gaps=[], user_message="讲讲单词")
    assert "英语话术示例" in ctx
    assert "apple" in ctx.lower() or "词汇" in ctx
    assert "混合运算" not in ctx.split("话术示例")[0]


def test_grader_apostrophe_and_punctuation_fuzzy() -> None:
    g = Grader()
    q = Question(
        question_id="q2",
        unit_id="english-g3-starter",
        knowledge_point_id="kp-en-g3-grammar-basic",
        stem="expand",
        answer_type=AnswerType.exact,
        expected_answer="do not",
        explanation="",
        default_error_code="GRAMMAR_ERROR",
    )
    assert g.grade(q, "don't").correct is True
    assert g.grade(q, "Do not").correct is True
    assert g.grade(q, "do-not").correct is True

    q_cn = Question(
        question_id="q3",
        unit_id="chinese-g2-sentence-basic",
        knowledge_point_id="kp-g2-punct-period",
        stem="句号",
        answer_type=AnswerType.exact,
        expected_answer="。",
        explanation="",
        default_error_code="PUNCTUATION_ERROR",
    )
    assert g.grade(q_cn, "。").correct is True
    assert g.grade(q_cn, ".").correct is False


def test_grader_exact_case_insensitive() -> None:
    g = Grader()
    q = Question(
        question_id="q1",
        unit_id="english-g3-starter",
        knowledge_point_id="kp-en-g3-vocab-basic",
        stem="apple?",
        answer_type=AnswerType.exact,
        expected_answer="apple",
        explanation="",
        default_error_code="VOCAB_GAP",
    )
    assert g.grade(q, "Apple").correct is True
    assert g.grade(q, "APPLE").correct is True
    assert g.grade(q, "appl").correct is False


def test_english_remediation_skill_mapping() -> None:
    from agent_platform.learning.remediation_skills import skill_for_error_code

    assert skill_for_error_code("SPELLING_ERROR").skill_id == "remediation/english_vocab_drill"
    assert skill_for_error_code("GRAMMAR_ERROR").skill_id == "remediation/concept_v1"

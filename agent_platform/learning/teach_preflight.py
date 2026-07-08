"""讲新课预检：L1 软强制 catalog 对齐 + explain_kp 要点注入（不经孩子可见）。"""

from __future__ import annotations

import os
import re
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, resolve_data_root
from agent_platform.learning.kp_catalog import GradeBoundaryError, get_kp_catalog_service
from agent_platform.learning.learning_catalog_lookup import lookup_units
from agent_platform.learning.learning_focus import set_learning_focus
from agent_platform.learning.prompts import detect_teach_intent
from agent_platform.learning.student_context import StudentContextService

TEACH_PREFLIGHT_ENV = "STUDENT_JARVIS_TEACH_PREFLIGHT"

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8}

_SUBJECT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"小学语文|语文"), "语文"),
    (re.compile(r"小学数学|数学"), "数学"),
    (re.compile(r"小学英语|英语"), "英语"),
]

_UNIT_PATTERNS = [
    re.compile(r"第\s*([一二三四五六七八1-8])\s*单元"),
    re.compile(r"([1-8])\s*单元"),
    re.compile(r"unit\s*0?(\d)", re.I),
]


def _parse_unit_num(text: str) -> Optional[int]:
    for pat in _UNIT_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        raw = m.group(1)
        if raw in _CN_NUM:
            return _CN_NUM[raw]
        try:
            return int(raw)
        except ValueError:
            continue
    return None


def _parse_subject(text: str) -> Optional[str]:
    for pat, subject in _SUBJECT_PATTERNS:
        if pat.search(text):
            return subject
    return None


def _pick_teaching_kp(kp_ids: list[str]) -> Optional[str]:
    if not kp_ids:
        return None
    priority = ("-overview", "-intro", "-vocab", "-sentences", "-reading", "-lesson")
    for suffix in priority:
        for kid in kp_ids:
            if suffix in kid:
                return kid
    return kp_ids[0]


def parse_teach_target(message: str) -> tuple[Optional[str], Optional[int]]:
    text = (message or "").strip()
    if not text:
        return None, None
    return _parse_subject(text), _parse_unit_num(text)


def run_teach_preflight(student_id: str, message: str) -> str:
    """若识别为讲新课意图，返回注入 pre_llm 的预检块（空串表示跳过）。"""
    if not detect_teach_intent(message):
        return ""

    cfg = load_student_learning_config()
    data_root = resolve_data_root(cfg)
    ctx_svc = StudentContextService(data_root=data_root)
    if not ctx_svc.exists(student_id):
        return ""

    ctx = ctx_svc.get(student_id)
    grade_level = ctx.curriculum.grade_level
    if grade_level is None:
        grade_level = get_kp_catalog_service().resolve_grade_level(ctx.curriculum.grade)

    subject, unit_num = parse_teach_target(message)
    lookup = lookup_units(
        grade_level=int(grade_level),
        subject=subject,
        unit_num=unit_num,
    )
    if not lookup.success:
        err = lookup.error or "catalog lookup failed"
        if "grade boundary" in err.lower() or "cannot access unit grade" in err.lower():
            return (
                "## 本轮讲新课预检（系统）\n"
                f"- 孩子请求的内容可能超纲：{err}\n"
                "- 请温和说明「这个还没学到」，拉回当前三年级单元；不要硬讲超纲内容。"
            )
        if subject or unit_num:
            return (
                "## 本轮讲新课预检（系统）\n"
                f"- catalog 未能唯一匹配（{err}）。\n"
                "- 请先追问「数学还是语文的第几单元？」再讲；勿编造 unit。\n"
                "- 禁止向孩子复述本段系统说明。"
            )
        return ""

    if lookup.ambiguous:
        names = "、".join(f"「{c.unit_title}」" for c in lookup.candidates[:4])
        return (
            "## 本轮讲新课预检（系统）\n"
            f"- 匹配到多个单元：{names}\n"
            "- 请先让孩子确认具体单元，再 learning_focus_set + explain_kp。\n"
            "- 禁止向孩子复述本段系统说明。"
        )

    unit = lookup.unit
    if unit is None:
        return ""

    try:
        get_kp_catalog_service().assert_student_may_access_unit(int(grade_level), unit.unit_id)
    except GradeBoundaryError as exc:
        return (
            "## 本轮讲新课预检（系统）\n"
            f"- 年级边界：{exc}\n"
            "- 请温和拉回当前年级内容；勿向孩子复述本段。"
        )

    focus = set_learning_focus(student_id, unit.unit_id, data_root=data_root)
    kp_ids = [k["knowledge_point_id"] for k in (unit.knowledge_points or [])]
    teach_kp = _pick_teaching_kp(kp_ids)

    teaching_lines: list[str] = []
    if teach_kp:
        from agent_platform.learning.kp_wiki_sync import KpWikiSyncService

        wiki_ctx = KpWikiSyncService().fetch_teaching_context(teach_kp)
        if wiki_ctx.get("success"):
            desc = (wiki_ctx.get("description_text") or "").strip()
            title = wiki_ctx.get("title") or teach_kp
            if desc:
                teaching_lines.append(f"**{title}**（{teach_kp}）\n{desc[:1200]}")
            elif wiki_ctx.get("has_wiki"):
                teaching_lines.append(f"**{title}**：Wiki 有索引但讲解要点待补充，请诚实说明教案在完善。")
            else:
                teaching_lines.append(
                    f"**{title}**：尚无 Wiki 讲解要点；请诚实说教案在补充，勿编造课文原文。"
                )

    switched = "（本轮已写回持久单元）" if not focus.already_current else "（单元本就一致，勿向孩子提切换）"
    lines = [
        "## 本轮讲新课预检（系统自动，勿向学生复述）",
        f"- 目标单元：{focus.subject} · {focus.unit_title}（{focus.unit_id}）{switched}",
    ]
    if teaching_lines:
        lines.append("- explain_kp 要点（请据此讲解）：")
        lines.extend(teaching_lines)
    else:
        lines.append(f"- 请先调用 explain_kp（建议 kp：{teach_kp or '单元内首个 KP'}）。")
    lines.append("- 直接开始自然讲解；禁止说「已对齐」「不用切换」等框架用语。")
    return "\n".join(lines)


def set_teach_preflight_env(block: str, env: dict[str, str]) -> None:
    if block:
        env[TEACH_PREFLIGHT_ENV] = block


def pop_teach_preflight_from_env() -> str:
    return (os.environ.pop(TEACH_PREFLIGHT_ENV, None) or "").strip()

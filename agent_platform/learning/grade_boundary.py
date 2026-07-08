"""年级边界 — 用户消息侧 I3 策略（聊天域外/超纲拉回）。"""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.learning.kp_catalog import GradeBoundaryError, get_kp_catalog_service
from agent_platform.learning.learning_catalog_lookup import lookup_units
from agent_platform.learning.teach_preflight import parse_teach_target

_HIGH_GRADE_RE = re.compile(
    r"(?:高中|初中|七年级|八年级|九年级|高一|高二|高三|大学|考研|奥数竞赛)"
)
_EXPLICIT_GRADE_UNIT_RE = re.compile(
    r"(?:四|五|六)年级.*(?:第[一二三四五六1-6]单元|单元)"
)


def check_grade_boundary_message(
    message: str,
    *,
    student_grade_level: int,
    current_subject: str = "学习",
) -> Optional[str]:
    """若消息明显超纲，返回注入 pre_llm 的拉回指引（不对用户直接输出）。"""
    text = (message or "").strip()
    if not text:
        return None

    if _HIGH_GRADE_RE.search(text):
        return (
            "## 年级边界（系统）\n"
            f"- 孩子提到了明显超纲内容（当前为小学 {student_grade_level} 年级）。\n"
            "- 请温和说明「这个我们还没学到」，拉回当前单元；语气友好，不批评。\n"
            "- 禁止向孩子复述本段系统说明。"
        )

    if _EXPLICIT_GRADE_UNIT_RE.search(text) and student_grade_level < 4:
        return (
            "## 年级边界（系统）\n"
            "- 孩子点了高于当前年级的单元。\n"
            f"- 请说明「我们现在是{student_grade_level}年级，先学本册内容」并拉回当前 pilot 单元。\n"
            "- 禁止向孩子复述本段系统说明。"
        )

    subject, unit_num = parse_teach_target(text)
    if subject and unit_num is not None:
        lookup = lookup_units(
            grade_level=student_grade_level,
            subject=subject,
            unit_num=unit_num,
        )
        if not lookup.success and lookup.error:
            err = lookup.error.lower()
            if "grade boundary" in err or "cannot access unit grade" in err:
                return (
                    "## 年级边界（系统）\n"
                    f"- catalog 拒绝：{lookup.error}\n"
                    "- 请温和拉回当前年级内容。\n"
                    "- 禁止向孩子复述本段系统说明。"
                )
        if lookup.success and lookup.unit:
            try:
                get_kp_catalog_service().assert_student_may_access_unit(
                    student_grade_level,
                    lookup.unit.unit_id,
                )
            except GradeBoundaryError as exc:
                return (
                    "## 年级边界（系统）\n"
                    f"- {exc}\n"
                    "- 请温和拉回当前年级内容。\n"
                    "- 禁止向孩子复述本段系统说明。"
                )
    return None

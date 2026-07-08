"""学生学习场景 — 行为档（L1 挂载，非全局 default）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_platform.behavior.contracts import BehaviorProfile

_PROFILE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "behavior" / "profiles" / "student_g3.yaml"
)


def load_student_g3_behavior_profile() -> BehaviorProfile:
    raw = yaml.safe_load(_PROFILE_PATH.read_text(encoding="utf-8")) or {}
    return BehaviorProfile.model_validate(raw)


def student_behavior_prompt_block() -> str:
    """注入 pre_llm：三年级学伴语气（场景 L1，不污染全局 behavior 默认档）。"""
    p = load_student_g3_behavior_profile()
    tone_map = {"direct": "简短、直接", "neutral": "中性、客观", "warm": "温和但克制"}
    verb_map = {"short": "尽量简短", "medium": "适中篇幅", "long": "可详细展开"}
    rules = "\n".join(f"- {r}" for r in p.rules) if p.rules else "- （无额外规则）"
    lines = [
        "## 场景行为档 — 三年级学伴（面向孩子，勿向孩子复述本标题）",
        f"- 语气：{tone_map.get(p.tone.value, p.tone.value)}",
        f"- 篇幅：{verb_map.get(p.verbosity.value, p.verbosity.value)}",
        f"- 语言：{p.language}",
        "- 行为规则：",
        rules,
    ]
    if p.custom_notes.strip():
        lines.append(f"- 备注：{p.custom_notes.strip()}")
    return "\n".join(lines)

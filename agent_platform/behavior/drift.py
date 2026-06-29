"""Persona drift detection — heuristic scoring (M7)."""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.behavior.contracts import BehaviorProfile, DriftReport, Verbosity


def detect_drift(
    text: str,
    profile: BehaviorProfile,
    config: Optional[dict] = None,
) -> DriftReport:
    from agent_platform.behavior._config import load_behavior_config

    cfg = config or load_behavior_config()
    drift_cfg = cfg.get("drift") or {}
    if not drift_cfg.get("enabled", True):
        return DriftReport(drift_score=0.0, drifted=False)

    violations: list[str] = []
    score_parts: list[float] = []

    if profile.verbosity == Verbosity.short:
        max_chars = int(drift_cfg.get("max_chars_short", 280))
        if len(text) > max_chars:
            violations.append(f"verbosity_exceeded:{len(text)}>{max_chars}")
            score_parts.append(min(1.0, (len(text) - max_chars) / max(max_chars, 1)))

    fillers = drift_cfg.get("filler_patterns") or []
    for pat in fillers:
        if pat in text:
            violations.append(f"filler:{pat}")
            score_parts.append(0.4)

    if profile.tone.value == "direct":
        verbose_openers = ("首先", "总的来说", "让我来为你", "非常感谢你的提问")
        for opener in verbose_openers:
            if text.strip().startswith(opener):
                violations.append(f"indirect_opener:{opener}")
                score_parts.append(0.25)

    for rule in profile.rules:
        if "简短" in rule and len(text.split()) > 80:
            violations.append("rule_short_reply")
            score_parts.append(0.3)
            break

    drift_score = min(1.0, sum(score_parts)) if score_parts else 0.0
    threshold = float(drift_cfg.get("threshold", 0.35))
    drifted = drift_score >= threshold

    reinforcement = None
    if drifted:
        rules_hint = "；".join(profile.rules[:3]) if profile.rules else "保持简短直接"
        reinforcement = f"【行为档提醒】请遵守设定：{rules_hint}"

    return DriftReport(
        drift_score=round(drift_score, 3),
        drifted=drifted,
        violations=violations,
        reinforcement=reinforcement,
        details={"threshold": threshold, "verbosity": profile.verbosity.value},
    )

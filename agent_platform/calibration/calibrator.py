"""Output calibration — confidence exposure + hedge rewrite (M7)."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_platform.calibration.contracts import (
    CalibrateRequest,
    CalibratedResponse,
    ConfidenceLevel,
)


def _score_to_level(score: float, cfg: dict) -> ConfidenceLevel:
    conf = cfg.get("confidence") or {}
    hi = float(conf.get("high_threshold", 0.75))
    lo = float(conf.get("low_threshold", 0.45))
    if score >= hi:
        return ConfidenceLevel.high
    if score <= lo:
        return ConfidenceLevel.low
    return ConfidenceLevel.medium


def _infer_confidence(req: CalibrateRequest) -> float:
    if req.confidence is not None:
        return req.confidence
    text = req.text.lower()
    hedge_markers = ("不确定", "可能", "也许", "大概", "我不清楚", "让我查", "i'm not sure", "maybe")
    if any(m in text for m in hedge_markers):
        return 0.35
    if req.has_tool_source or req.memory_backed:
        return 0.85
    return 0.6


def _has_source_markers(text: str) -> bool:
    markers = (
        "查到了",
        "根据",
        "工具返回",
        "记忆显示",
        "记录显示",
        "source:",
        "来自 wiki",
        "我查到",
    )
    return any(m in text for m in markers)


def _detect_sensitive(text: str, cfg: dict) -> list[str]:
    patterns = cfg.get("sensitive_patterns") or {}
    require = cfg.get("require_source_for") or []
    flags: list[str] = []
    for kind in require:
        pat = patterns.get(kind)
        if not pat:
            continue
        if re.search(pat, text, re.IGNORECASE):
            flags.append(f"unsourced_{kind}")
    return flags


def _rewrite_low_confidence(text: str, cfg: dict) -> str:
    prefix = cfg.get("low_confidence_prefix") or "我不太确定，"
    rewrite = cfg.get("uncertain_rewrite") or f"{prefix}让我查一下再告诉你。"
    stripped = text.strip()
    if any(stripped.startswith(p) for p in (prefix, "我不确定", "我不太确定")):
        return stripped
    if len(stripped) < 24:
        return rewrite
    return f"{prefix}{stripped}"


def calibrate_output(req: CalibrateRequest, config: Optional[dict] = None) -> CalibratedResponse:
    """Post-process assistant text: expose low confidence, hedge unsourced claims."""
    from agent_platform.calibration._config import load_calibration_config

    cfg = config or load_calibration_config()
    if not cfg.get("enabled", True):
        score = _infer_confidence(req)
        return CalibratedResponse(
            text=req.text,
            confidence_level=_score_to_level(score, cfg),
            confidence_score=score,
        )

    score = _infer_confidence(req)
    flags = _detect_sensitive(req.text, cfg)
    has_source = req.has_tool_source or req.memory_backed or _has_source_markers(req.text)

    if flags and not has_source:
        score = min(score, float((cfg.get("confidence") or {}).get("low_threshold", 0.45)))

    level = _score_to_level(score, cfg)
    out_text = req.text
    rewritten = False

    if level == ConfidenceLevel.low:
        out_text = _rewrite_low_confidence(req.text, cfg)
        rewritten = out_text.strip() != req.text.strip()
        flags.append("hedged")

    return CalibratedResponse(
        text=out_text,
        confidence_level=level,
        confidence_score=score,
        rewritten=rewritten,
        flags=flags,
        original_text=req.text if rewritten else None,
    )

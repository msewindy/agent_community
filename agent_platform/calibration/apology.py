"""Apology + memory supersede on user correction (US-6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from agent_platform.calibration.contracts import CorrectionResult, UserCorrectionRequest
from agent_platform.memory.contracts import MemoryCorrectRequest, MemoryKind, MemoryWriteRequest

if TYPE_CHECKING:
    from agent_platform.memory.service import MemoryService


def format_apology(new_value: str, config: Optional[dict] = None) -> str:
    from agent_platform.calibration._config import load_calibration_config

    cfg = config or load_calibration_config()
    ap = cfg.get("apology") or {}
    template = ap.get("template") or "抱歉，我记错了。现在更新为 {new_value}，原记录已废止。"
    return template.format(new_value=new_value)


def handle_user_correction(
    req: UserCorrectionRequest,
    memory_service: MemoryService,
    config: Optional[dict] = None,
) -> CorrectionResult:
    """User says agent was wrong → apologize + supersede old memory record."""
    from agent_platform.calibration._config import load_calibration_config
    from agent_platform.memory.trace import new_trace_id

    cfg = config or load_calibration_config()
    tid = req.trace_id or new_trace_id()

    replacement = MemoryWriteRequest(
        content=req.new_value,
        device_id=req.device_id or memory_service.default_device_id,
        kind=MemoryKind.fact,
        trace_id=tid,
        metadata={"corrected_from": req.record_id, "old_value": req.old_value},
    )
    correct_req = MemoryCorrectRequest(
        record_id=req.record_id,
        reason=req.reason,
        replacement=replacement,
        trace_id=tid,
    )

    try:
        new_rec = memory_service.correct(correct_req)
    except KeyError:
        return CorrectionResult(
            success=False,
            apology_text="抱歉，找不到要更正的记录。",
            old_record_id=req.record_id,
            trace_id=tid,
            details={"error": "record_not_found"},
        )

    apology = format_apology(req.new_value, cfg) if (cfg.get("apology") or {}).get("enabled", True) else ""

    return CorrectionResult(
        success=True,
        apology_text=apology,
        old_record_id=req.record_id,
        new_record_id=new_rec.record_id,
        tombstoned=True,
        trace_id=tid,
        details={"old_value": req.old_value, "new_value": req.new_value},
    )

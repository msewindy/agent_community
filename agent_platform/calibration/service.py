"""Calibration facade — calibrate output + handle corrections (M7)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_platform.calibration._config import load_calibration_config, resolve_log_path
from agent_platform.calibration.apology import format_apology, handle_user_correction
from agent_platform.calibration.calibrator import calibrate_output
from agent_platform.calibration.contracts import (
    CalibrateRequest,
    CalibratedResponse,
    CorrectionResult,
    UserCorrectionRequest,
)
from agent_platform.memory.service import MemoryService, get_memory_service


class CalibrationService:
    def __init__(
        self,
        config: Optional[dict] = None,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        self._cfg = config or load_calibration_config()
        self._mem = memory_service or get_memory_service()
        self._log_path = resolve_log_path(self._cfg)

    def calibrate(self, req: CalibrateRequest) -> CalibratedResponse:
        result = calibrate_output(req, self._cfg)
        self._append_event(
            "calibrate",
            req.trace_id,
            {
                "level": result.confidence_level.value,
                "score": result.confidence_score,
                "rewritten": result.rewritten,
                "flags": result.flags,
            },
        )
        return result

    def correct(self, req: UserCorrectionRequest) -> CorrectionResult:
        result = handle_user_correction(req, self._mem, self._cfg)
        self._append_event(
            "correction",
            result.trace_id,
            {
                "success": result.success,
                "old_record_id": result.old_record_id,
                "new_record_id": result.new_record_id,
            },
        )
        try:
            from agent_platform.evolution.bridge import bridge_enabled, forward_m7_correction

            if result.success and bridge_enabled():
                forward_m7_correction(req, result)
        except Exception:
            pass
        return result

    def apology_preview(self, new_value: str) -> str:
        return format_apology(new_value, self._cfg)

    def _append_event(self, kind: str, trace_id: Optional[str], payload: dict) -> None:
        audit = self._cfg.get("audit") or {}
        if not audit.get("enabled", True):
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        line = f"- `{ts}` **{kind}** trace={trace_id or '-'} {payload}\n"
        if not self._log_path.is_file():
            self._log_path.write_text("# Calibration audit\n\n", encoding="utf-8")
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(line)

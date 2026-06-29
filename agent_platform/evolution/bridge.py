"""M7 calibration → C7 evolution bridge (Phase 3)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agent_platform.calibration.contracts import CorrectionResult, UserCorrectionRequest

logger = logging.getLogger(__name__)


def bridge_enabled(cfg: dict | None = None) -> bool:
    from agent_platform.evolution._config import load_evolution_config

    cfg = cfg or load_evolution_config()
    bridge = cfg.get("bridge") or {}
    return bool(bridge.get("m7_enabled", True))


def forward_m7_correction(
    req: "UserCorrectionRequest",
    result: "CorrectionResult",
    *,
    evolution_service=None,
) -> dict:
    """After M7 memory supersede, update L1/L5 skill lifecycle."""
    if not result.success:
        return {"forwarded": False, "reason": "m7_failed"}
    if not bridge_enabled():
        return {"forwarded": False, "reason": "bridge_disabled"}

    if evolution_service is None:
        from agent_platform.evolution.service import get_evolution_service

        evolution_service = get_evolution_service()

    note = f"{req.old_value} → {req.new_value}"
    user_msg = req.reason or "user_correction"
    out = evolution_service.on_user_correction(
        user_message=user_msg,
        correction_note=note,
        old_value=req.old_value,
        new_value=req.new_value,
        trace_id=result.trace_id,
    )
    logger.info("evolution bridge: %s", out)
    return out

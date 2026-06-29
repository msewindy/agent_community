"""Hermes plugin: agent-calibration — US-6 calibrate + US-3 behavior (M7)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_repo_on_path() -> None:
    base = Path(__file__).resolve().parent
    root = os.environ.get("AGENT_COMMUNITY_ROOT", "").strip()
    if not root:
        marker = base / "AGENT_COMMUNITY_ROOT"
        if marker.is_file():
            root = marker.read_text(encoding="utf-8").strip()
    if not root:
        root = str(base.parents[3])
    s = str(Path(root))
    if s not in sys.path:
        sys.path.insert(0, s)
    os.environ.setdefault("AGENT_COMMUNITY_ROOT", s)


def register(ctx) -> None:
    _ensure_repo_on_path()
    from agent_platform.integrations.hermes.calibration_tools import register_m7_hermes_tools

    register_m7_hermes_tools(ctx)
    logger.info(
        "agent-calibration plugin: calibrate, correction, behavior_status, get_prompt, update, drift"
    )

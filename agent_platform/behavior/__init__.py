"""M7 behavior profile — 它的设定 + drift detection (US-3)."""

from agent_platform.behavior.contracts import (
    BehaviorProfile,
    BehaviorProfileUpdate,
    DriftReport,
    Tone,
    Verbosity,
)
from agent_platform.behavior.service import BehaviorService

__all__ = [
    "BehaviorService",
    "BehaviorProfile",
    "BehaviorProfileUpdate",
    "DriftReport",
    "Tone",
    "Verbosity",
]

#!/usr/bin/env python3
"""M7 D1 — calibration + behavior smoke."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    from agent_platform.behavior.contracts import BehaviorProfileUpdate, Tone, Verbosity
    from agent_platform.behavior.service import BehaviorService
    from agent_platform.behavior.store import BehaviorStore
    from agent_platform.calibration.contracts import (
        CalibrateRequest,
        ConfidenceLevel,
        UserCorrectionRequest,
    )
    from agent_platform.calibration.service import CalibrationService
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService

    td = tempfile.mkdtemp(prefix="m7_d1_")
    behavior_root = Path(td) / "behavior"
    calib_log = Path(td) / "calib.log.md"

    cal_cfg = {
        "enabled": True,
        "confidence": {"high_threshold": 0.75, "low_threshold": 0.45},
        "low_confidence_prefix": "我不太确定，",
        "uncertain_rewrite": "我不太确定，让我查一下再告诉你。",
        "require_source_for": ["version"],
        "sensitive_patterns": {"version": r"(?:v|版本\s*)[\d.]+"},
        "apology": {"enabled": True, "template": "抱歉，我记错了。现在更新为 {new_value}，原记录已废止。"},
        "audit": {"enabled": True, "log_path": str(calib_log)},
    }
    beh_cfg = {
        "enabled": True,
        "default_profile": {
            "tone": "direct",
            "verbosity": "short",
            "language": "zh-CN",
            "rules": ["回复尽量简短直接"],
        },
        "store": {"root": str(behavior_root), "profile_file": "profile.yaml"},
        "drift": {
            "enabled": True,
            "threshold": 0.35,
            "max_chars_short": 280,
            "filler_patterns": ["作为一个AI", "很高兴为你"],
        },
        "panel": {"host": "127.0.0.1", "port": 8767},
    }

    mem = MemoryService(adapter=MockMemAdapter(), config={"backend": "mock", "gate": {"enabled": False}})
    cal = CalibrationService(config=cal_cfg, memory_service=mem)
    beh = BehaviorService(
        config=beh_cfg,
        store=BehaviorStore(behavior_root / "profile.yaml", default_profile=beh_cfg["default_profile"]),
    )

    low = cal.calibrate(CalibrateRequest(text="版本号是 v0.3", confidence=0.9))
    if low.confidence_level != ConfidenceLevel.low or "不太确定" not in low.text:
        print(f"FAIL calibrate: {low}", file=sys.stderr)
        return 1
    print("OK   calibrate low confidence + unsourced version")

    rec = mem.write("文档版本号是 v0.2", trace_id="m7-smoke")
    corr = cal.correct(
        UserCorrectionRequest(
            record_id=rec.record_id,
            old_value="v0.2",
            new_value="文档版本号是 v0.3",
            trace_id="m7-corr",
        )
    )
    if not corr.success or "抱歉" not in corr.apology_text:
        print(f"FAIL correction: {corr}", file=sys.stderr)
        return 1
    search = mem.search("v0.3")
    if not any("v0.3" in h.content for h in search.hits):
        print("FAIL search after supersede", file=sys.stderr)
        return 1
    print("OK   correction apology + supersede")

    block = beh.system_prompt_block()
    if "它的设定" not in block:
        print("FAIL system prompt block", file=sys.stderr)
        return 1
    print("OK   behavior system prompt block")

    drift = beh.check_drift("作为一个AI，" + "很高兴为你服务。" * 20)
    if not drift.drifted:
        print(f"FAIL drift: {drift}", file=sys.stderr)
        return 1
    print("OK   drift detection")

    beh.update_profile(BehaviorProfileUpdate(rules=["测试规则"], tone=Tone.direct, verbosity=Verbosity.short))
    if "测试规则" not in beh.get_profile().rules:
        print("FAIL profile persist", file=sys.stderr)
        return 1
    print("OK   behavior profile persist")

    print("accept_m7_smoke_d1: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

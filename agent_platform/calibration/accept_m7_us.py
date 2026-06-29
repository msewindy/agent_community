#!/usr/bin/env python3
"""M7 D6–D10 — US-6 + US-3 后半 formal acceptance."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> bool:
    print(f"FAIL {msg}", file=sys.stderr)
    return False


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _isolated_cfg() -> tuple[dict, dict, Path]:
    td = tempfile.mkdtemp(prefix="m7_us_")
    root = Path(td)
    cal_cfg = {
        "enabled": True,
        "confidence": {"high_threshold": 0.75, "low_threshold": 0.45},
        "low_confidence_prefix": "我不太确定，",
        "require_source_for": ["version", "date", "number"],
        "sensitive_patterns": {
            "version": r"(?:v|版本\s*)[\d.]+",
            "date": r"\d{4}[-/年]\d{1,2}",
            "number": r"(?<!\w)\d+(?:\.\d+)?(?!\w)",
        },
        "apology": {"enabled": True, "template": "抱歉，我记错了。现在更新为 {new_value}，原记录已废止。"},
        "audit": {"enabled": True, "log_path": str(root / "calib.log.md")},
    }
    beh_cfg = {
        "enabled": True,
        "default_profile": {
            "tone": "direct",
            "verbosity": "short",
            "language": "zh-CN",
            "rules": ["回复尽量简短直接", "避免过度拟人化"],
        },
        "store": {"root": str(root / "behavior"), "profile_file": "profile.yaml"},
        "drift": {
            "enabled": True,
            "threshold": 0.35,
            "max_chars_short": 280,
            "filler_patterns": ["作为一个AI", "很高兴为你"],
        },
        "panel": {"host": "127.0.0.1", "port": 8767},
    }
    return cal_cfg, beh_cfg, root


def _services(root: Path, cal_cfg: dict, beh_cfg: dict):
    from agent_platform.behavior.service import BehaviorService
    from agent_platform.behavior.store import BehaviorStore
    from agent_platform.calibration.service import CalibrationService
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService

    mem = MemoryService(adapter=MockMemAdapter(), config={"backend": "mock", "gate": {"enabled": False}})
    cal = CalibrationService(config=cal_cfg, memory_service=mem)
    store = BehaviorStore(
        Path(beh_cfg["store"]["root"]) / beh_cfg["store"]["profile_file"],
        default_profile=beh_cfg["default_profile"],
    )
    beh = BehaviorService(config=beh_cfg, store=store)
    return cal, beh, mem


def m7_a1_low_confidence() -> bool:
    """US-6：低置信 / 无 source 版本号 → 暴露不确定。"""
    from agent_platform.calibration.contracts import CalibrateRequest, ConfidenceLevel

    cal_cfg, beh_cfg, root = _isolated_cfg()
    cal, _, _ = _services(root, cal_cfg, beh_cfg)
    r = cal.calibrate(CalibrateRequest(text="那个版本号是 v0.2", confidence=0.85))
    if r.confidence_level != ConfidenceLevel.low:
        return _fail(f"M7 A1 confidence level: {r.confidence_level}")
    if "不太确定" not in r.text and "不确定" not in r.text:
        return _fail(f"M7 A1 rewrite: {r.text}")
    _ok("M7 A1 US-6 low confidence exposed + hedged")
    return True


def m7_a2_tool_source_ok() -> bool:
    """US-6：有工具来源时可给出确定答案。"""
    from agent_platform.calibration.contracts import CalibrateRequest, ConfidenceLevel

    cal_cfg, beh_cfg, root = _isolated_cfg()
    cal, _, _ = _services(root, cal_cfg, beh_cfg)
    r = cal.calibrate(
        CalibrateRequest(
            text="查到了，版本号是 v0.2",
            confidence=0.5,
            has_tool_source=True,
        )
    )
    if r.confidence_level == ConfidenceLevel.low:
        return _fail(f"M7 A2 should not hedge with source: {r}")
    _ok("M7 A2 US-6 tool-backed answer kept")
    return True


def m7_a3_correction_supersede() -> bool:
    """US-6：用户纠错 → 道歉 + supersede + 下次返回新值。"""
    from agent_platform.calibration.contracts import UserCorrectionRequest

    cal_cfg, beh_cfg, root = _isolated_cfg()
    cal, _, mem = _services(root, cal_cfg, beh_cfg)
    rec = mem.write("项目版本号是 v0.2", trace_id="us6-write")
    corr = cal.correct(
        UserCorrectionRequest(
            record_id=rec.record_id,
            old_value="v0.2",
            new_value="项目版本号是 v0.3",
            trace_id="us6-correct",
        )
    )
    if not corr.success:
        return _fail(f"M7 A3 correction failed: {corr}")
    if "抱歉" not in corr.apology_text:
        return _fail(f"M7 A3 apology missing excuse-free text: {corr.apology_text}")
    if "借口" in corr.apology_text or "但是" in corr.apology_text:
        return _fail("M7 A3 apology should not make excuses")

    hits = mem.search("版本")
    if not any("v0.3" in h.content for h in hits.hits):
        return _fail(f"M7 A3 search should return v0.3: {hits.hits}")
    if any("v0.2" in h.content for h in hits.hits):
        return _fail("M7 A3 old value still active in search")
    _ok("M7 A3 US-6 apology + supersede + recall updated")
    return True


def m7_a4_behavior_persist() -> bool:
    """US-3：行为档持久化 + system 注入。"""
    from agent_platform.behavior.contracts import BehaviorProfileUpdate

    cal_cfg, beh_cfg, root = _isolated_cfg()
    _, beh1, _ = _services(root, cal_cfg, beh_cfg)
    beh1.apply_preference_hint("我喜欢直接简短的回应")
    block1 = beh1.system_prompt_block()

    _, beh2, _ = _services(root, cal_cfg, beh_cfg)
    block2 = beh2.system_prompt_block()
    if "简短" not in block1 or "简短" not in block2:
        return _fail("M7 A4 behavior profile not persisted across reload")
    if "它的设定" not in block2:
        return _fail("M7 A4 missing injection header")
    _ok("M7 A4 US-3 behavior profile persist + inject")
    return True


def m7_a5_drift() -> bool:
    """US-3：漂移检测 + reinforcement。"""
    cal_cfg, beh_cfg, root = _isolated_cfg()
    _, beh, _ = _services(root, cal_cfg, beh_cfg)
    verbose = "作为一个AI，" + "很高兴为你服务，让我详细解释一下。" * 15
    report = beh.check_drift(verbose)
    if not report.drifted:
        return _fail(f"M7 A5 drift not detected: {report}")
    if not report.reinforcement:
        return _fail("M7 A5 missing reinforcement hint")
    _ok("M7 A5 US-3 drift detection + reinforcement")
    return True


def m7_a6_settings_panel() -> bool:
    """US-3：设定面板可见可改。"""
    from agent_platform.api.settings_panel import create_app
    from agent_platform.behavior.service import BehaviorService
    from agent_platform.behavior.store import BehaviorStore

    cal_cfg, beh_cfg, root = _isolated_cfg()
    store = BehaviorStore(
        Path(beh_cfg["store"]["root"]) / beh_cfg["store"]["profile_file"],
        default_profile=beh_cfg["default_profile"],
    )
    svc = BehaviorService(config=beh_cfg, store=store)
    client = TestClient(create_app(config=beh_cfg, service=svc))

    page = client.get("/")
    if page.status_code != 200 or "它的设定" not in page.text:
        return _fail("M7 A6 panel HTML")

    updated = client.put(
        "/api/behavior/profile",
        json={"rules": ["可见可改：直接简短"], "tone": "direct", "verbosity": "short"},
    ).json()
    if "可见可改" not in " ".join(updated.get("rules", [])):
        return _fail(f"M7 A6 PUT profile: {updated}")
    _ok("M7 A6 US-3 settings panel visible + editable")
    return True


def m7_a7_hermes_tools() -> bool:
    """Hermes 工具链。"""
    from agent_platform.integrations.hermes.calibration_tools import (
        agent_behavior_get_prompt,
        agent_calibrate_output,
        check_m7_available,
    )
    from agent_platform.integrations.hermes.tools import bootstrap_agent_platform

    bootstrap_agent_platform()
    if not check_m7_available():
        return _fail("M7 A7 m7 tools unavailable")

    cal = json.loads(agent_calibrate_output({"text": "版本 v1.0"}))
    if not cal.get("rewritten") and cal.get("confidence_level") != "low":
        return _fail(f"M7 A7 calibrate tool: {cal}")

    pr = json.loads(agent_behavior_get_prompt({}))
    if "它的设定" not in pr.get("system_prompt", ""):
        return _fail("M7 A7 get_prompt")
    _ok("M7 A7 Hermes calibration + behavior tools")
    return True


def m7_d5_regression() -> bool:
    import os
    import subprocess

    script = _REPO / "agent_platform" / "calibration" / "accept_m7_smoke.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--skip-pytest"],
        cwd=str(_REPO),
        env={**os.environ, "PYTHONPATH": str(_REPO)},
        check=False,
    )
    if proc.returncode != 0:
        return _fail("M7 D5 accept_m7_smoke regression")
    _ok("M7 D5 regression accept_m7_smoke")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="M7 US acceptance")
    p.add_argument("--skip-d5", action="store_true")
    args = p.parse_args()

    steps = [
        m7_a1_low_confidence,
        m7_a2_tool_source_ok,
        m7_a3_correction_supersede,
        m7_a4_behavior_persist,
        m7_a5_drift,
        m7_a6_settings_panel,
        m7_a7_hermes_tools,
    ]
    if not args.skip_d5:
        steps.append(m7_d5_regression)
    else:
        _skip("D5 regression accept_m7_smoke")

    for fn in steps:
        if not fn():
            print("accept_m7_us: FAIL", file=sys.stderr)
            return 1

    print("accept_m7_us: PASS — US-6 / US-3 后半 automated acceptance OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

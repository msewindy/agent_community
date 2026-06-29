#!/usr/bin/env python3
"""M4 D6–D10 — US-2 formal acceptance (mock + optional Reachy hardware)."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

VISION_QUESTION = "看下桌上那本书叫什么名字？"
NON_VISION = "今天上海天气怎么样？"
CAMERA_OFF_SNIPPET = "摄像头当前关闭"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> bool:
    print(f"FAIL {msg}", file=sys.stderr)
    return False


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _perception_cfg(root: Path, *, camera: bool, backend: str = "mock") -> dict:
    return {
        "backend": backend,
        "device": {"default_id": "us2-accept-device"},
        "store": {"root": str(root), "save_captures": True},
        "policy": {"camera_enabled": camera, "microphone_enabled": False},
        "vision": {"enabled": True, "provider": "mock", "on_demand_only": True},
        "bus": {"memory_observe": False},
        "capture": {"require_opencv": True},
    }


def _opencv_ok() -> bool:
    try:
        from agent_platform.perception.frames import opencv_available

        return opencv_available()
    except Exception:
        return False


def _isolated_root() -> Path:
    td = tempfile.mkdtemp(prefix="us2_")
    root = Path(td) / "perception"
    root.mkdir(parents=True, exist_ok=True)
    return root


def us2_a1_non_vision_no_describe(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: 非视觉问法不触发 describe（按需）。"""
    from agent_platform.perception.bus import reset_event_bus
    from agent_platform.perception.orchestrate import PerceptionOrchestrator
    from agent_platform.perception.service import PerceptionService

    reset_event_bus()
    svc = PerceptionService(config=_perception_cfg(root, camera=True), store_root=root)
    orch = PerceptionOrchestrator(service=svc, auto_enable_camera_in_session=False)
    turn = orch.handle_message(NON_VISION, session_id="us2-a1")
    if turn.vision_intent:
        return _fail("US-2 A1: non-vision flagged as vision_intent")
    if turn.describe and turn.describe.allowed:
        return _fail("US-2 A1: describe ran without vision intent")
    visions = list((root / "visions").glob("*.json")) if (root / "visions").is_dir() else []
    if visions:
        return _fail("US-2 A1: vision records created without intent")
    _ok("US-2 A1 on-demand — non-vision does not trigger describe")
    return True


def us2_a2_camera_off_message(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: 摄像头关 + 视觉问法 → 明确中文提示。"""
    from agent_platform.perception.bus import reset_event_bus
    from agent_platform.perception.orchestrate import PerceptionOrchestrator
    from agent_platform.perception.service import PerceptionService

    reset_event_bus()
    svc = PerceptionService(config=_perception_cfg(root, camera=False), store_root=root)
    orch = PerceptionOrchestrator(service=svc, auto_enable_camera_in_session=False)
    turn = orch.handle_message(VISION_QUESTION, session_id="us2-a2")
    if not turn.reply_override or CAMERA_OFF_SNIPPET not in turn.reply_override:
        return _fail(f"US-2 A2: expected camera off message, got {turn.reply_override!r}")
    if turn.describe and turn.describe.allowed:
        return _fail("US-2 A2: describe should not run when camera off")
    _ok("US-2 A2 camera off → 摄像头当前关闭…")
    return True


def us2_a3_camera_on_book_answer(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: 摄像头开 + 视觉问法 → mock VLM 书名。"""
    from agent_platform.perception.bus import reset_event_bus
    from agent_platform.perception.orchestrate import PerceptionOrchestrator
    from agent_platform.perception.service import PerceptionService

    reset_event_bus()
    svc = PerceptionService(config=_perception_cfg(root, camera=True), store_root=root)
    orch = PerceptionOrchestrator(service=svc, auto_enable_camera_in_session=False)
    turn = orch.handle_message(VISION_QUESTION, session_id="us2-a3")
    if not turn.describe or not turn.describe.allowed:
        return _fail(f"US-2 A3: describe failed {turn.meta}")
    desc = turn.describe.description or ""
    if "思考" not in desc and "Fast" not in desc:
        return _fail(f"US-2 A3: missing book title in {desc[:80]}")
    if not turn.prompt_prefix:
        return _fail("US-2 A3: missing prompt_prefix for Hermes")
    _ok("US-2 A3 camera on → describe 《思考，快与慢》+ prompt_prefix")
    return True


def us2_a4_policy_toggle(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: 用户开关 policy（等同 UI 一键关/开摄像头）。"""
    from agent_platform.perception.service import PerceptionService

    svc = PerceptionService(config=_perception_cfg(root, camera=True), store_root=root)
    svc.set_policy(camera_enabled=False)
    if svc.policy.camera_enabled:
        return _fail("US-2 A4: policy camera off failed")
    svc.set_policy(camera_enabled=True)
    if not svc.policy.camera_enabled:
        return _fail("US-2 A4: policy camera on failed")
    pol_path = root / "policy.json"
    if not pol_path.is_file():
        return _fail("US-2 A4: policy.json not persisted")
    data = json.loads(pol_path.read_text(encoding="utf-8"))
    if not data.get("camera_enabled"):
        return _fail("US-2 A4: policy.json camera_enabled false after on")
    _ok("US-2 A4 policy.json toggle camera off/on")
    return True


def us2_a5_hermes_policy_tool(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: Hermes agent_perception_policy 读写开关。"""
    try:
        from agent_platform.integrations.hermes import perception_tools as pt
    except ImportError as e:
        _skip(f"US-2 A5 hermes tools: {e}")
        return True

    cfg = _perception_cfg(root, camera=False)
    svc_factory = lambda: __import__(  # noqa: E731
        "agent_platform.perception.service", fromlist=["PerceptionService"]
    ).PerceptionService(config=cfg, store_root=root)
    pt._get_perception_service = svc_factory  # type: ignore[method-assign]

    off = json.loads(pt.agent_perception_policy({"camera": "off"}))
    if not off.get("success") or off.get("camera_enabled") is not False:
        return _fail(f"US-2 A5 policy off: {off}")
    on = json.loads(pt.agent_perception_policy({"camera": "on"}))
    if not on.get("success") or not on.get("camera_enabled"):
        return _fail(f"US-2 A5 policy on: {on}")
    _ok("US-2 A5 Hermes agent_perception_policy off/on")
    return True


def us2_a6_event_bus_audit(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: 事件总线审计 events.jsonl + session。"""
    from agent_platform.perception.bus import reset_event_bus
    from agent_platform.perception.orchestrate import PerceptionOrchestrator
    from agent_platform.perception.service import PerceptionService

    reset_event_bus()
    svc = PerceptionService(config=_perception_cfg(root, camera=True), store_root=root)
    orch = PerceptionOrchestrator(service=svc)
    orch.handle_message(VISION_QUESTION, session_id="us2-a6")
    events_path = root / "events.jsonl"
    if not events_path.is_file():
        return _fail("US-2 A6: events.jsonl missing")
    topics = {
        json.loads(ln)["topic"]
        for ln in events_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    }
    if "perception.describe" not in topics:
        return _fail(f"US-2 A6: topics={topics}")
    sess = root / "sessions" / "us2-a6.jsonl"
    if not sess.is_file():
        return _fail("US-2 A6: session jsonl missing")
    _ok("US-2 A6 events.jsonl + sessions/*.jsonl audit")
    return True


def us2_a7_voice_bridge(root: Path | None = None) -> bool:
    root = root or _isolated_root()
    """US-2: Voice 会话联动（关摄像头 → reply_override）。"""
    from agent_platform.voice.perception_bridge import VoicePerceptionBridge

    cfg_voice = {
        "perception": {
            "enabled": True,
            "auto_enable_camera_in_session": False,
        }
    }
    from agent_platform.perception.orchestrate import PerceptionOrchestrator
    from agent_platform.perception.service import PerceptionService

    svc = PerceptionService(config=_perception_cfg(root, camera=False), store_root=root)
    bridge = VoicePerceptionBridge.from_voice_config(cfg_voice)
    bridge._orch = PerceptionOrchestrator(  # noqa: SLF001
        service=svc,
        auto_enable_camera_in_session=False,
    )
    turn = bridge.pre_turn(VISION_QUESTION, session_id="us2-voice")
    if not turn.reply_override or CAMERA_OFF_SNIPPET not in turn.reply_override:
        return _fail("US-2 A7 voice bridge camera off")
    _ok("US-2 A7 VoicePerceptionBridge camera off → reply_override")
    return True


def us2_reachy_hardware() -> bool:
    """US-2 D9: 真机 Reachy SDK 探测 + 可选抓帧（不强制 VLM）。"""
    from agent_platform.perception.adapters.reachy_sdk import ReachySdkAdapter, sdk_available
    from agent_platform.perception.contracts import CaptureRequest, PerceptionModality
    from agent_platform.perception.service import PerceptionService

    if not sdk_available():
        _skip("US-2 Reachy: reachy_mini not installed (pip install 'reachy_mini[opencv]')")
        return True

    adapter = ReachySdkAdapter(media_backend="default", probe_media=False)
    st = adapter.probe()
    if not st.reachable:
        _skip(f"US-2 Reachy: not reachable — {st.message}")
        return True

    _ok(f"US-2 Reachy probe: {st.message}")

    with tempfile.TemporaryDirectory(prefix="us2_reachy_") as td:
        root = Path(td)
        cfg = _perception_cfg(root, camera=True, backend="reachy_sdk")
        svc = PerceptionService(config=cfg, store_root=root)
        svc.set_policy(camera_enabled=True)
        cap = svc.capture(
            CaptureRequest(modality=PerceptionModality.vision, scene="us2-reachy", save_frame=True)
        )
        if not cap.allowed:
            _skip(f"US-2 Reachy capture: {cap.reason_code} — {cap.message}")
            return True
        if cap.saved_frame and (root / cap.saved_frame.image_path).is_file():
            _ok(f"US-2 Reachy capture frame → {cap.frame_path}")
        else:
            _skip("US-2 Reachy capture: no saved frame (OpenCV?)")
    return True


def run_d5_regression() -> bool:
    from agent_platform.perception.accept_m4_smoke import main as smoke_main

    old_argv = sys.argv
    try:
        sys.argv = ["accept_m4_smoke", "--skip-pytest"]
        if smoke_main() != 0:
            return _fail("US-2 D5 regression accept_m4_smoke")
    finally:
        sys.argv = old_argv
    _ok("US-2 D5 regression accept_m4_smoke (--skip-pytest)")
    return True


def print_manual_checklist() -> None:
    print(
        """
--- 手动验收清单（D7–D9，签字用）---

D7 Hermes（需 hermes + agent_perception 插件）:
  1. hermes plugins enable agent-perception && hermes tools enable agent_perception
  2. agent_perception_policy camera=off
  3. 用户：看下桌上那本书叫什么名字？
     → Agent 应说明摄像头关闭，或调用 describe 得到 policy 拒绝
  4. agent_perception_policy camera=on → 再问视觉 → 应有书名描述

D8 Voice 全链路:
  PYTHONPATH=. python agent_platform/voice/smoke_pipeline.py -t "看下桌上那本书叫什么名字？"
  → 关摄像头时应 TTS 播报「摄像头当前关闭…」

D9 真机 Reachy:
  perception.yaml: backend: reachy_sdk
  PYTHONPATH=. python agent_platform/perception/cli_perception.py status
  PYTHONPATH=. python agent_platform/perception/cli_perception.py capture --enable-camera

签字表：docs/M4-us-acceptance.md §4
"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description="M4 US-2 acceptance (D6–D10)")
    p.add_argument("--reachy", action="store_true", help="probe/capture real Reachy if online")
    p.add_argument("--skip-d5", action="store_true", help="skip accept_m4_smoke regression")
    p.add_argument("--skip-hermes", action="store_true")
    args = p.parse_args()

    print("=== accept_m4_us2 (US-2) ===\n")

    if not _opencv_ok():
        print("FAIL OpenCV required for US-2 automated acceptance", file=sys.stderr)
        print("  uv pip install opencv-python-headless --index-url https://pypi.tuna.tsinghua.edu.cn/simple")
        return 1

    ok = True
    steps = [
        us2_a1_non_vision_no_describe,
        us2_a2_camera_off_message,
        us2_a3_camera_on_book_answer,
        us2_a4_policy_toggle,
        us2_a6_event_bus_audit,
        us2_a7_voice_bridge,
    ]
    for fn in steps:
        if not fn():
            ok = False

    if not args.skip_hermes and not us2_a5_hermes_policy_tool():
        ok = False
    elif args.skip_hermes:
        _skip("US-2 A5 hermes policy tool")

    if not args.skip_d5 and not run_d5_regression():
        ok = False
    elif args.skip_d5:
        _skip("D5 regression")

    if args.reachy and not us2_reachy_hardware():
        ok = False
    elif not args.reachy:
        _skip("US-2 Reachy hardware (pass --reachy when robot online)")

    print()
    if ok:
        print("accept_m4_us2: PASS — US-2 automated acceptance OK")
        print_manual_checklist()
        return 0
    print("accept_m4_us2: FAIL", file=sys.stderr)
    print_manual_checklist()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

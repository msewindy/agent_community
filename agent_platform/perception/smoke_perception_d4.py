#!/usr/bin/env python3
"""M4 D4 smoke — event bus + session + voice orchestration (no Hermes)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def run_smoke() -> int:
    from agent_platform.perception.bus import reset_event_bus
    from agent_platform.perception.frames import opencv_available
    from agent_platform.perception.orchestrate import PerceptionOrchestrator
    from agent_platform.perception.service import PerceptionService
    from agent_platform.perception.session import latest_vision_context, load_session_records
    from agent_platform.voice.perception_bridge import VoicePerceptionBridge

    if not opencv_available():
        print("SKIP: OpenCV not installed")
        return 0

    reset_event_bus()
    with tempfile.TemporaryDirectory(prefix="perception-d4-") as td:
        root = Path(td)
        cfg = {
            "backend": "mock",
            "store": {"root": str(root)},
            "policy": {"camera_enabled": False},
            "vision": {"enabled": True, "provider": "mock"},
            "bus": {"memory_observe": False},
        }
        svc = PerceptionService(config=cfg, store_root=root)
        orch = PerceptionOrchestrator(service=svc, auto_enable_camera_in_session=False)

        off = orch.handle_message(
            "看下桌上那本书叫什么名字？",
            session_id="d4-smoke-session",
        )
        if off.reply_override is None or "摄像头" not in off.reply_override:
            print("FAIL camera off", off.reply_override)
            return 1
        events_jsonl = root / "events.jsonl"
        if not events_jsonl.is_file():
            print("FAIL no events.jsonl")
            return 1
        print("camera off + bus audit: OK")

        svc.set_policy(camera_enabled=True)
        ok = orch.handle_message(
            "看下桌上那本书叫什么名字？",
            session_id="d4-smoke-session",
        )
        if not ok.prompt_prefix or not ok.describe or not ok.describe.allowed:
            print(f"FAIL describe turn {ok.meta}")
            return 1

        sess = load_session_records(root / "sessions", "d4-smoke-session")
        if not sess:
            print("FAIL session jsonl empty")
            return 1
        ctx = latest_vision_context(root / "sessions", "d4-smoke-session")
        if not ctx or "思考" not in ctx.description:
            print("FAIL session vision context", ctx)
            return 1

        voice_cfg = {
            "perception": {
                "enabled": True,
                "auto_enable_camera_in_session": True,
            }
        }
        bridge = VoicePerceptionBridge.from_voice_config(voice_cfg)
        bridge._orch = orch  # noqa: SLF001
        prompt = bridge.apply_to_hermes_prompt("看下桌上那本书叫什么名字？", ok)
        if "视觉描述" not in prompt:
            print("FAIL hermes prompt prefix")
            return 1

        lines = events_jsonl.read_text(encoding="utf-8").strip().splitlines()
        topics = {json.loads(ln)["topic"] for ln in lines if ln.strip()}
        if "perception.describe" not in topics:
            print("FAIL missing describe topic in bus", topics)
            return 1

        print(f"describe + session + bus topics={topics}")
        print("M4 D4 smoke: PASS")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())

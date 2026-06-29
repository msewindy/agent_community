#!/usr/bin/env python3
"""M4 D3 smoke — mock VLM + capture → US-2 book answer."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def run_smoke() -> int:
    from agent_platform.perception.contracts import DescribeRequest
    from agent_platform.perception.frames import opencv_available
    from agent_platform.perception.service import PerceptionService
    from agent_platform.perception.vision_intent import is_vision_intent

    if not opencv_available():
        print("SKIP: OpenCV not installed")
        return 0

    assert is_vision_intent("看下桌上那本书叫什么名字？")
    assert not is_vision_intent("今天天气怎么样")

    with tempfile.TemporaryDirectory(prefix="perception-d3-") as td:
        root = Path(td)
        cfg = {
            "backend": "mock",
            "store": {"root": str(root), "save_captures": True},
            "policy": {"camera_enabled": False},
            "vision": {"enabled": True, "provider": "mock"},
            "capture": {"require_opencv": True},
        }
        svc = PerceptionService(config=cfg, store_root=root)

        off = svc.describe(DescribeRequest(question="看下桌上那本书叫什么名字？"))
        if off.allowed or off.reason_code != "camera_disabled":
            print(f"FAIL expected camera_disabled, got {off.reason_code}")
            return 1
        if "摄像头" not in off.message:
            print("FAIL missing camera off message")
            return 1
        print("camera off gate: OK")

        svc.set_policy(camera_enabled=True)
        ok = svc.describe(
            DescribeRequest(question="看下桌上那本书叫什么名字？", scene="desk")
        )
        if not ok.allowed or not ok.description:
            print(f"FAIL describe {ok.reason_code} {ok.message}")
            return 1
        if "思考" not in ok.description and "Fast" not in ok.description:
            print(f"FAIL US-2 book answer: {ok.description[:120]}")
            return 1

        vision_file = root / "visions"
        if not any(vision_file.glob("*.json")):
            print("FAIL no vision record")
            return 1

        print(f"describe OK: {ok.description[:80]}…")
        print(f"  model={ok.model} latency_ms={ok.latency_ms}")
        print("M4 D3 smoke: PASS")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())

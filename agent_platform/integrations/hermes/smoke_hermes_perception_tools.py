#!/usr/bin/env python3
"""Smoke Hermes perception tool handlers (no full Hermes runtime)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from agent_platform.integrations.hermes import perception_tools as pt  # noqa: E402


def main() -> int:
    from agent_platform.perception.frames import opencv_available

    if not opencv_available():
        print("SKIP: opencv not installed")
        return 0

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = {
            "backend": "mock",
            "store": {"root": str(root)},
            "vision": {"enabled": True, "provider": "mock"},
        }

        def _svc():
            from agent_platform.perception.service import PerceptionService

            return PerceptionService(config=cfg, store_root=root)

        pt._get_perception_service = _svc  # type: ignore[method-assign]

        off = json.loads(
            pt.agent_perception_describe(
                {"question": "看下桌上那本书叫什么名字？"},
                current_session_id="smoke-perception",
            )
        )
        if off.get("success") is not False or off.get("reason_code") != "camera_disabled":
            print("FAIL camera off", off)
            return 1

        on = json.loads(
            pt.agent_perception_describe(
                {
                    "question": "看下桌上那本书叫什么名字？",
                    "enable_camera": True,
                },
                current_session_id="smoke-perception",
            )
        )
        if not on.get("success"):
            print("FAIL describe", on)
            return 1
        if "思考" not in (on.get("description") or ""):
            print("FAIL book title", on)
            return 1

        pol = json.loads(pt.agent_perception_policy({"camera": "on"}))
        if not pol.get("camera_enabled"):
            print("FAIL policy", pol)
            return 1

    print("smoke_hermes_perception_tools: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

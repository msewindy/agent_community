#!/usr/bin/env python3
"""M4 D1 smoke — perception config, mock capture, ObserveEvent."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.memory.contracts import ObserveSource
from agent_platform.perception.contracts import CaptureRequest, PerceptionModality
from agent_platform.perception.service import PerceptionService
from agent_platform.perception.store import ensure_store, validate_store


def run_smoke() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "perception"
        cfg = {
            "backend": "mock",
            "device": {"default_id": "smoke-reachy"},
            "policy": {"camera_enabled": False, "microphone_enabled": False},
            "store": {"root": str(root), "auto_init": True, "save_captures": True},
        }
        ensure_store(root)
        if validate_store(root):
            print("FAIL validate_store", file=sys.stderr)
            return 1

        svc = PerceptionService(config=cfg, store_root=root)
        st = svc.status()
        if not st.connected:
            print("FAIL status", file=sys.stderr)
            return 1

        denied = svc.capture(CaptureRequest(modality=PerceptionModality.vision))
        if denied.allowed:
            print("FAIL should deny when camera off", file=sys.stderr)
            return 1

        svc.set_policy(camera_enabled=True)
        ok = svc.capture(
            CaptureRequest(
                modality=PerceptionModality.vision,
                scene="desk",
                save_frame=False,
            )
        )
        if not ok.allowed or not ok.event:
            print(f"FAIL capture {ok}", file=sys.stderr)
            return 1
        if ok.event.source != ObserveSource.reachy:
            print("FAIL observe source", file=sys.stderr)
            return 1

        log = (root / "events.log.md").read_text(encoding="utf-8")
        if "capture" not in log:
            print("FAIL events log", file=sys.stderr)
            return 1

        print(f"smoke_perception_d1: PASS event_id={ok.event.event_id[:8]}…")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    sys.exit(main())

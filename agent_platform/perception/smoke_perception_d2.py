#!/usr/bin/env python3
"""M4 D2 smoke — OpenCV JPEG + .meta.json under perception_data/captures/."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def run_smoke() -> int:
    from agent_platform.perception.contracts import CaptureRequest, PerceptionModality
    from agent_platform.perception.frames import opencv_available
    from agent_platform.perception.service import PerceptionService

    if not opencv_available():
        print("SKIP: OpenCV not installed — pip install opencv-python-headless")
        return 0

    with tempfile.TemporaryDirectory(prefix="perception-d2-") as td:
        root = Path(td)
        cfg = {
            "backend": "mock",
            "store": {"root": str(root), "save_captures": True},
            "policy": {"camera_enabled": True},
            "capture": {"require_opencv": True},
        }
        svc = PerceptionService(config=cfg, store_root=root)
        st = svc.status()
        print(f"status: {st.backend.value} {st.message}")

        ok = svc.capture(CaptureRequest(modality=PerceptionModality.vision, scene="d2-smoke"))
        if not ok.allowed:
            print(f"FAIL capture: {ok.reason_code} {ok.message}")
            return 1
        if not ok.saved_frame:
            print("FAIL: no saved_frame")
            return 1

        img = root / ok.saved_frame.image_path
        meta = root / ok.saved_frame.meta_path
        if not img.is_file() or img.stat().st_size < 100:
            print(f"FAIL: bad image {img}")
            return 1
        if not meta.is_file():
            print(f"FAIL: missing meta {meta}")
            return 1

        frames = svc.list_frames(limit=5)
        print(f"capture OK: {img.name} {ok.saved_frame.width}x{ok.saved_frame.height}")
        print(f"  sha256={ok.saved_frame.sha256[:16]}…")
        print(f"  index entries={len(frames)}")
        print("M4 D2 smoke: PASS")
        return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())

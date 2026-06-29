"""M4 D2 — frame bundle save / list."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.perception.contracts import CaptureRequest, PerceptionModality
from agent_platform.perception.frames import opencv_available, save_frame_bundle, synthetic_test_frame
from agent_platform.perception.service import PerceptionService


@pytest.mark.skipif(not opencv_available(), reason="opencv not installed")
def test_save_frame_bundle(tmp_path: Path):
    root = tmp_path / "store"
    cap_dir = root / "captures"
    frame = synthetic_test_frame(64, 48)
    saved = save_frame_bundle(
        store_root=root,
        captures_dir=cap_dir,
        frame=frame,
        trace_id="test-trace-001",
        scene="unit",
        backend="mock",
    )
    assert (root / saved.image_path).is_file()
    assert (root / saved.meta_path).is_file()
    assert saved.width == 64
    assert saved.height == 48
    assert len(saved.sha256) == 64


@pytest.mark.skipif(not opencv_available(), reason="opencv not installed")
def test_mock_capture_writes_jpeg(tmp_path: Path):
    root = tmp_path / "p"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root), "save_captures": True},
        "policy": {"camera_enabled": True},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    ok = svc.capture(CaptureRequest(modality=PerceptionModality.vision, scene="desk"))
    assert ok.allowed
    assert ok.saved_frame is not None
    assert (root / ok.saved_frame.image_path).stat().st_size > 0
    listed = svc.list_frames(3)
    assert len(listed) >= 1

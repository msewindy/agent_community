"""M4 D1/D2 — mock adapter and service tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.perception.contracts import CaptureRequest, PerceptionModality
from agent_platform.perception.frames import opencv_available
from agent_platform.perception.service import PerceptionService


@pytest.mark.skipif(not opencv_available(), reason="opencv not installed")
def test_policy_gate_and_capture(tmp_path: Path):
    root = tmp_path / "p"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root)},
        "policy": {"camera_enabled": False},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    denied = svc.capture(CaptureRequest(modality=PerceptionModality.vision))
    assert not denied.allowed
    assert denied.reason_code == "camera_disabled"

    svc.set_policy(camera_enabled=True)
    ok = svc.capture(CaptureRequest(modality=PerceptionModality.vision, scene="test"))
    assert ok.allowed
    assert ok.event is not None
    assert ok.saved_frame is not None
    assert (root / ok.saved_frame.image_path).is_file()
    assert (root / "events.log.md").is_file()

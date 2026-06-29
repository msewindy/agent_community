"""M4 D1 — perception contract tests."""

from __future__ import annotations

from agent_platform.memory.contracts import ObserveSource
from agent_platform.perception.contracts import (
    PerceptionModality,
    capture_to_observe_event,
    export_json_schemas,
)


def test_capture_to_observe_event():
    ev = capture_to_observe_event(
        text="desk scene",
        trace_id="t1",
        device_id="d1",
        scene="desk",
        frame_path="captures/x.jpg",
        modality=PerceptionModality.vision,
    )
    assert ev.source == ObserveSource.reachy
    assert ev.text == "desk scene"
    assert "vision" in ev.modality


def test_export_schemas():
    bundle = export_json_schemas()
    assert "PerceptionPolicy" in bundle["definitions"]

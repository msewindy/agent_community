"""Mock Reachy adapter — synthetic OpenCV frames (M4 D1/D2)."""

from __future__ import annotations

from pathlib import Path

from agent_platform.perception.contracts import (
    CaptureRequest,
    CaptureResult,
    PerceptionBackend,
    PerceptionModality,
    PerceptionPolicy,
    PerceptionStatus,
    capture_to_observe_event,
)
from agent_platform.perception.frames import (
    FrameSaveError,
    opencv_available,
    save_frame_bundle,
    synthetic_test_frame,
)


class MockReachyAdapter:
    def __init__(
        self,
        *,
        jpeg_quality: int = 92,
        require_opencv: bool = True,
        frame_width: int = 320,
        frame_height: int = 240,
    ) -> None:
        self._jpeg_quality = jpeg_quality
        self._require_opencv = require_opencv
        self._w = frame_width
        self._h = frame_height

    def probe(self) -> PerceptionStatus:
        return PerceptionStatus(
            backend=PerceptionBackend.mock,
            connected=True,
            reachable=True,
            sdk_available=False,
            message="mock adapter (synthetic frames)",
            details={"opencv": opencv_available()},
        )

    def capture(
        self,
        req: CaptureRequest,
        policy: PerceptionPolicy,
        *,
        captures_dir: Path,
        store_root: Path,
        device_id: str,
        save_frame: bool,
    ) -> CaptureResult:
        if req.modality == PerceptionModality.vision and not policy.camera_enabled and not req.force:
            return CaptureResult(
                allowed=False,
                reason_code="camera_disabled",
                message="Camera is off — enable via policy or CLI.",
            )
        if req.modality == PerceptionModality.audio and not policy.microphone_enabled and not req.force:
            return CaptureResult(
                allowed=False,
                reason_code="microphone_disabled",
                message="Microphone is off — enable via policy or CLI.",
            )

        saved = None
        frame_path: str | None = None
        if req.modality == PerceptionModality.vision and save_frame and req.save_frame:
            try:
                frame = synthetic_test_frame(self._w, self._h)
                saved = save_frame_bundle(
                    store_root=store_root,
                    captures_dir=captures_dir,
                    frame=frame,
                    trace_id=req.trace_id,
                    scene=req.scene,
                    device_id=device_id,
                    backend="mock",
                    jpeg_quality=self._jpeg_quality,
                    require_opencv=self._require_opencv,
                )
                frame_path = saved.image_path
            except FrameSaveError as e:
                return CaptureResult(
                    allowed=False,
                    reason_code="frame_save_error",
                    message=str(e),
                )

        text = (
            f"[mock vision] scene={req.scene or 'desk'} "
            f"用户桌上有一本书（模拟 US-2）；frame={frame_path or 'none'}"
            if req.modality == PerceptionModality.vision
            else "[mock audio] ambient room tone"
        )
        event = capture_to_observe_event(
            text=text,
            trace_id=req.trace_id,
            device_id=device_id,
            scene=req.scene,
            frame_path=frame_path,
            modality=req.modality,
            extra={
                "mock": True,
                "sha256": saved.sha256 if saved else None,
                "width": saved.width if saved else None,
                "height": saved.height if saved else None,
            },
        )
        return CaptureResult(
            allowed=True,
            reason_code="ok",
            event=event,
            frame_path=frame_path,
            saved_frame=saved,
            message="mock capture ok",
        )

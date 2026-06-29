"""Reachy Mini SDK adapter — probe + OpenCV frame capture (M4 D2)."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any, Optional

from agent_platform.perception.contracts import (
    CaptureRequest,
    CaptureResult,
    PerceptionBackend,
    PerceptionModality,
    PerceptionPolicy,
    PerceptionStatus,
    capture_to_observe_event,
)
from agent_platform.perception.frames import FrameSaveError, opencv_available, save_frame_bundle


def sdk_available() -> bool:
    return importlib.util.find_spec("reachy_mini") is not None


def _capture_media_backend(configured: str, for_capture: bool) -> str:
    if for_capture:
        if configured in ("no_media", "", None):
            return "default"
        return configured
    return "no_media"


class ReachySdkAdapter:
    def __init__(
        self,
        *,
        media_backend: str = "default",
        connect_timeout_s: float = 15.0,
        frame_timeout_s: float = 20.0,
        jpeg_quality: int = 92,
        require_opencv: bool = True,
        probe_media: bool = True,
    ) -> None:
        self._media_backend = media_backend
        self._connect_timeout_s = connect_timeout_s
        self._frame_timeout_s = frame_timeout_s
        self._jpeg_quality = jpeg_quality
        self._require_opencv = require_opencv
        self._probe_media = probe_media

    def probe(self) -> PerceptionStatus:
        if not sdk_available():
            return PerceptionStatus(
                backend=PerceptionBackend.reachy_sdk,
                connected=False,
                reachable=False,
                sdk_available=False,
                message="reachy_mini package not installed",
            )
        if self._require_opencv and not opencv_available():
            return PerceptionStatus(
                backend=PerceptionBackend.reachy_sdk,
                connected=False,
                reachable=False,
                sdk_available=True,
                message="OpenCV not installed (required for D2 frame save)",
                details={"opencv": False},
            )
        try:
            from reachy_mini import ReachyMini

            backend = _capture_media_backend(self._media_backend, for_capture=False)
            with ReachyMini(media_backend=backend) as _mini:
                details: dict[str, Any] = {
                    "media_backend_probe": backend,
                    "opencv": opencv_available(),
                }
                if self._probe_media:
                    cap_backend = _capture_media_backend(self._media_backend, for_capture=True)
                    details["media_backend_capture"] = cap_backend
                    try:
                        with ReachyMini(media_backend=cap_backend) as cam:
                            frame = cam.media.get_frame()
                            deadline = time.time() + min(self._frame_timeout_s, 8.0)
                            while frame is None and time.time() < deadline:
                                time.sleep(0.3)
                                frame = cam.media.get_frame()
                            details["camera_warmup_ok"] = frame is not None
                            if frame is not None:
                                details["frame_shape"] = list(frame.shape)
                    except Exception as cam_e:
                        details["camera_warmup_error"] = str(cam_e)

                return PerceptionStatus(
                    backend=PerceptionBackend.reachy_sdk,
                    connected=True,
                    reachable=True,
                    sdk_available=True,
                    message="ReachyMini() connected",
                    details=details,
                )
        except Exception as e:
            return PerceptionStatus(
                backend=PerceptionBackend.reachy_sdk,
                connected=False,
                reachable=False,
                sdk_available=True,
                message=f"Reachy connect failed: {e}",
                details={"error": str(e)},
            )

    def _grab_frame(self, backend: str) -> Any:
        from reachy_mini import ReachyMini

        with ReachyMini(media_backend=backend) as mini:
            frame = mini.media.get_frame()
            deadline = time.time() + self._frame_timeout_s
            while frame is None and time.time() < deadline:
                time.sleep(0.4)
                frame = mini.media.get_frame()
            return frame

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
                message="Camera disabled by policy",
            )
        if not sdk_available():
            return CaptureResult(
                allowed=False,
                reason_code="sdk_missing",
                message="pip install reachy_mini",
            )
        if req.modality != PerceptionModality.vision:
            return CaptureResult(
                allowed=False,
                reason_code="unsupported_modality",
                message="reachy_sdk D2 supports vision only",
            )
        if save_frame and req.save_frame and not opencv_available():
            return CaptureResult(
                allowed=False,
                reason_code="opencv_missing",
                message="pip install opencv-python-headless",
            )

        cap_backend = _capture_media_backend(self._media_backend, for_capture=True)
        try:
            frame = self._grab_frame(cap_backend)
            if frame is None:
                return CaptureResult(
                    allowed=False,
                    reason_code="frame_timeout",
                    message=f"get_frame() timed out ({cap_backend})",
                )

            saved = None
            frame_path: str | None = None
            if save_frame and req.save_frame:
                saved = save_frame_bundle(
                    store_root=store_root,
                    captures_dir=captures_dir,
                    frame=frame,
                    trace_id=req.trace_id,
                    scene=req.scene,
                    device_id=device_id,
                    backend=f"reachy_sdk:{cap_backend}",
                    jpeg_quality=self._jpeg_quality,
                    require_opencv=self._require_opencv,
                )
                frame_path = saved.image_path

            h, w = frame.shape[:2]
            text = (
                f"[reachy vision] saved {frame_path or 'no-file'} "
                f"{w}x{h} scene={req.scene or 'capture'}"
            )
            event = capture_to_observe_event(
                text=text,
                trace_id=req.trace_id,
                device_id=device_id,
                scene=req.scene,
                frame_path=frame_path,
                modality=req.modality,
                extra={
                    "width": int(w),
                    "height": int(h),
                    "backend": cap_backend,
                    "sha256": saved.sha256 if saved else None,
                },
            )
            return CaptureResult(
                allowed=True,
                reason_code="ok",
                event=event,
                frame_path=frame_path,
                saved_frame=saved,
                message="reachy frame captured and saved",
            )
        except FrameSaveError as e:
            return CaptureResult(allowed=False, reason_code="frame_save_error", message=str(e))
        except Exception as e:
            return CaptureResult(allowed=False, reason_code="capture_error", message=str(e))

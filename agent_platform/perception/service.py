"""perception_service facade — Reachy observe / capture (M4)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from agent_platform.memory.contracts import ObserveEvent, ObserveSource
from agent_platform.perception._config import load_perception_config, resolve_store_root
from agent_platform.perception.adapters.mock import MockReachyAdapter
from agent_platform.perception.adapters.reachy_sdk import ReachySdkAdapter
from agent_platform.perception.contracts import (
    CaptureRequest,
    CaptureResult,
    DescribeRequest,
    DescribeResult,
    PerceptionBackend,
    PerceptionModality,
    PerceptionPolicy,
    PerceptionPort,
    PerceptionStatus,
    capture_to_observe_event,
)
from agent_platform.perception.policy import load_policy, save_policy
from agent_platform.perception.frames import list_saved_frames
from agent_platform.perception.store import append_event_log, ensure_store
from agent_platform.perception.vlm import VlmPort, build_vlm_adapter, save_vision_record

_PUBLISH_CAPTURE = True
_PUBLISH_DESCRIBE = True


def _maybe_publish(topic: str, event: ObserveEvent, meta: dict | None = None) -> None:
    try:
        from agent_platform.perception.bus import get_event_bus

        get_event_bus().publish(topic, event, meta=meta)
    except Exception:
        pass


def _store_cfg(cfg: dict) -> dict:
    return cfg.get("store") or {}


def _capture_cfg(cfg: dict) -> dict:
    return cfg.get("capture") or {}


def _vision_cfg(cfg: dict) -> dict:
    return cfg.get("vision") or {}


_CAMERA_OFF_MSG = "摄像头当前关闭，无法完成视觉问答。你可以在设置中开启摄像头后再试。"


def _build_adapter(cfg: dict) -> PerceptionPort:
    backend = (cfg.get("backend") or "mock").lower()
    cap = _capture_cfg(cfg)
    jpeg_q = int(cap.get("jpeg_quality", 92))
    require_cv = bool(cap.get("require_opencv", True))
    if backend == "reachy_sdk":
        r = cfg.get("reachy") or {}
        return ReachySdkAdapter(
            media_backend=str(r.get("media_backend", "default")),
            connect_timeout_s=float(r.get("connect_timeout_s", 15)),
            frame_timeout_s=float(r.get("frame_timeout_s", 20)),
            jpeg_quality=jpeg_q,
            require_opencv=require_cv,
            probe_media=bool(r.get("probe_media", True)),
        )
    return MockReachyAdapter(
        jpeg_quality=jpeg_q,
        require_opencv=require_cv,
        frame_width=int(cap.get("mock_width", 320)),
        frame_height=int(cap.get("mock_height", 240)),
    )


class PerceptionService:
    """M4 facade: policy switches, SDK probe, capture → ObserveEvent."""

    def __init__(
        self,
        config: Optional[dict] = None,
        store_root: Optional[Path] = None,
        adapter: Optional[PerceptionPort] = None,
        vlm: Optional[VlmPort] = None,
    ) -> None:
        self._cfg = config or load_perception_config()
        self._layout = ensure_store(store_root or resolve_store_root(self._cfg))
        self._adapter = adapter or _build_adapter(self._cfg)
        self._vlm = vlm if vlm is not None else build_vlm_adapter(self._cfg)
        pol = self._cfg.get("policy") or {}
        self._policy = load_policy(
            self._layout.policy_path,
            PerceptionPolicy(
                camera_enabled=bool(pol.get("camera_enabled", False)),
                microphone_enabled=bool(pol.get("microphone_enabled", False)),
            ),
        )

    @property
    def policy(self) -> PerceptionPolicy:
        return self._policy

    @property
    def store_root(self) -> Path:
        return self._layout.root

    @property
    def default_device_id(self) -> str:
        return (self._cfg.get("device") or {}).get("default_id", "reachy-device")

    def status(self) -> PerceptionStatus:
        st = self._adapter.probe()
        st.camera_enabled = self._policy.camera_enabled
        st.microphone_enabled = self._policy.microphone_enabled
        return st

    def set_policy(
        self,
        *,
        camera_enabled: Optional[bool] = None,
        microphone_enabled: Optional[bool] = None,
    ) -> PerceptionPolicy:
        if camera_enabled is not None:
            self._policy.camera_enabled = camera_enabled
        if microphone_enabled is not None:
            self._policy.microphone_enabled = microphone_enabled
        save_policy(self._layout.policy_path, self._policy)
        return self._policy

    def capture(self, req: CaptureRequest) -> CaptureResult:
        save = bool(_store_cfg(self._cfg).get("save_captures", True))
        result = self._adapter.capture(
            req,
            self._policy,
            captures_dir=self._layout.captures_dir,
            store_root=self._layout.root,
            device_id=req.device_id or self.default_device_id,
            save_frame=save and req.save_frame,
        )
        if result.event:
            fp = result.frame_path or "no-frame"
            sha = result.saved_frame.sha256[:12] if result.saved_frame else "-"
            append_event_log(
                self._layout,
                f"capture {result.reason_code} trace={req.trace_id} "
                f"modality={req.modality.value} frame={fp} sha={sha}",
            )
            if _PUBLISH_CAPTURE:
                _maybe_publish(
                    "perception.capture",
                    result.event,
                    meta={"scene": req.scene, "reason_code": result.reason_code},
                )
        return result

    def list_frames(self, limit: int = 20):
        return list_saved_frames(self._layout.root, limit=limit)

    def observe_capture(self, req: CaptureRequest) -> ObserveEvent:
        """Capture and return ObserveEvent (raises on deny)."""
        result = self.capture(req)
        if not result.allowed or not result.event:
            raise PermissionError(result.message or result.reason_code)
        return result.event

    def vision_enabled(self) -> bool:
        return bool(_vision_cfg(self._cfg).get("enabled", False))

    def describe(self, req: DescribeRequest) -> DescribeResult:
        """US-2: on-demand capture + Qwen2-VL (or mock) — only when vision.enabled."""
        vis = _vision_cfg(self._cfg)
        if not self.vision_enabled():
            return DescribeResult(
                allowed=False,
                reason_code="vision_disabled",
                message="视觉描述未启用（perception.yaml vision.enabled）",
            )
        if not self._policy.camera_enabled and not req.force:
            return DescribeResult(
                allowed=False,
                reason_code="camera_disabled",
                message=_CAMERA_OFF_MSG,
            )

        frame_rel = req.frame_path
        trace_id = req.trace_id
        device_id = req.device_id or self.default_device_id

        if not frame_rel:
            cap = self.capture(
                CaptureRequest(
                    modality=PerceptionModality.vision,
                    scene=req.scene,
                    trace_id=trace_id,
                    device_id=device_id,
                    save_frame=True,
                    force=req.force,
                )
            )
            if not cap.allowed:
                return DescribeResult(
                    allowed=False,
                    reason_code=cap.reason_code,
                    message=cap.message,
                )
            frame_rel = cap.frame_path
            if not frame_rel:
                return DescribeResult(
                    allowed=False,
                    reason_code="no_frame",
                    message="capture succeeded but no frame on disk",
                )

        image_path = self._layout.root / frame_rel
        if not image_path.is_file():
            return DescribeResult(
                allowed=False,
                reason_code="frame_missing",
                message=f"frame not found: {frame_rel}",
            )

        t0 = time.perf_counter()
        try:
            description = self._vlm.describe(image_path, req.question)
        except Exception as e:
            return DescribeResult(
                allowed=False,
                reason_code="vlm_error",
                message=str(e),
                frame_path=frame_rel,
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        model_name = getattr(self._vlm, "model", "unknown")
        provider = getattr(self._vlm, "provider", "unknown")
        save_vision_record(
            self._layout.root,
            trace_id=trace_id,
            question=req.question,
            description=description,
            model=model_name,
            provider=provider,
            frame_path=frame_rel,
            latency_ms=latency_ms,
        )

        event = ObserveEvent(
            source=ObserveSource.reachy,
            modality=[PerceptionModality.vision.value],
            text=description,
            payload={
                "modality": PerceptionModality.vision.value,
                "frame_path": frame_rel,
                "question": req.question,
                "vlm_model": model_name,
                "vlm_provider": provider,
                "latency_ms": latency_ms,
                "on_demand": True,
            },
            trace_id=trace_id,
            device_id=device_id,
            scene=req.scene,
            raw_refs=[frame_rel],
        )
        append_event_log(
            self._layout,
            f"describe ok trace={trace_id} model={model_name} "
            f"latency_ms={latency_ms} frame={frame_rel}",
        )
        if _PUBLISH_DESCRIBE:
            pub_meta: dict = {
                "question": req.question,
                "model": model_name,
                "latency_ms": latency_ms,
            }
            if req.session_id:
                pub_meta["session_id"] = req.session_id
            _maybe_publish("perception.describe", event, meta=pub_meta)
        return DescribeResult(
            allowed=True,
            reason_code="ok",
            description=description,
            event=event,
            frame_path=frame_rel,
            model=model_name,
            latency_ms=latency_ms,
            message="vision describe ok",
        )

    def describe_for_user_message(self, user_message: str, *, scene: str = "desk") -> DescribeResult:
        """Convenience: run describe when message matches vision intent."""
        from agent_platform.perception.vision_intent import is_vision_intent

        if not is_vision_intent(user_message):
            return DescribeResult(
                allowed=False,
                reason_code="not_vision_intent",
                message="message does not look like a vision question",
            )
        return self.describe(DescribeRequest(question=user_message, scene=scene))

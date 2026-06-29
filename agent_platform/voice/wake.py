"""openWakeWord — keyword spotting (16 kHz chunks)."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass

import numpy as np

# openWakeWord expects 1280 samples @ 16 kHz per frame (80 ms)
OWW_FRAME_SAMPLES = 1280


@dataclass
class WakeHit:
    model_name: str
    score: float


class WakeWordDetector:
    def __init__(self, models: list[str] | None = None, *, threshold: float = 0.5) -> None:
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        self.threshold = threshold
        names = models or ["alexa"]
        try:
            download_models(model_names=[f"{n}_v0.1" for n in names])
        except Exception as exc:
            raise RuntimeError(
                "openWakeWord models missing. Retry when online:\n"
                "  python -c \"from openwakeword.utils import download_models;"
                " download_models(model_names=['alexa_v0.1'])\""
            ) from exc
        self._model = Model(wakeword_models=names, inference_framework="onnx")

    @property
    def model_names(self) -> list[str]:
        return list(self._model.models.keys())

    def score_frame(self, pcm_int16: np.ndarray) -> list[WakeHit]:
        if len(pcm_int16) != OWW_FRAME_SAMPLES:
            raise ValueError(f"expected {OWW_FRAME_SAMPLES} samples, got {len(pcm_int16)}")
        scores = self._model.predict(pcm_int16)
        hits: list[WakeHit] = []
        for name, value in scores.items():
            s = float(value)
            if s >= self.threshold:
                hits.append(WakeHit(model_name=name, score=s))
        return hits


def listen_for_wake(
    detector: WakeWordDetector,
    *,
    timeout_s: float = 30.0,
    device: int | None = None,
) -> WakeHit | None:
    """Block until wake word or timeout. Returns first hit or None."""
    import sounddevice as sd

    audio_q: queue.Queue[np.ndarray] = queue.Queue()
    deadline = time.perf_counter() + timeout_s
    buffer = np.array([], dtype=np.int16)

    def _callback(indata, _frames, _time, _status) -> None:
        audio_q.put(indata[:, 0].copy())

    stream = sd.InputStream(
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=OWW_FRAME_SAMPLES,
        device=device,
        callback=_callback,
    )

    with stream:
        while time.perf_counter() < deadline:
            try:
                block = audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            buffer = np.concatenate([buffer, block.astype(np.int16)])
            while len(buffer) >= OWW_FRAME_SAMPLES:
                frame = buffer[:OWW_FRAME_SAMPLES]
                buffer = buffer[OWW_FRAME_SAMPLES:]
                for hit in detector.score_frame(frame):
                    return hit
    return None

"""Silero VAD — speech segment boundaries on 16 kHz mono PCM (512-sample chunks)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch


# silero-vad @ 16 kHz requires exactly 512 samples per chunk
CHUNK_SAMPLES_16K = 512


@dataclass
class SpeechSegment:
    start_sample: int
    end_sample: int
    sample_rate: int = 16000

    @property
    def duration_ms(self) -> float:
        return (self.end_sample - self.start_sample) / self.sample_rate * 1000


class SileroVAD:
    """Thin wrapper around silero-vad VADIterator."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_silence_ms: int = 300,
        speech_pad_ms: int = 30,
    ) -> None:
        from silero_vad import load_silero_vad, VADIterator

        if sample_rate != 16000:
            raise ValueError("SileroVAD currently supports 16000 Hz only")
        self.sample_rate = sample_rate
        self._model = load_silero_vad()
        self._iterator = VADIterator(
            self._model,
            threshold=threshold,
            sampling_rate=sample_rate,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )

    def reset(self) -> None:
        self._iterator.reset_states()

    def process_chunk(self, pcm_int16: np.ndarray) -> list[SpeechSegment]:
        """Feed exactly *CHUNK_SAMPLES_16K* int16 mono samples."""
        if len(pcm_int16) != CHUNK_SAMPLES_16K:
            raise ValueError(
                f"expected {CHUNK_SAMPLES_16K} samples, got {len(pcm_int16)}"
            )
        wav = torch.from_numpy(pcm_int16.astype(np.int16)).float() / 32768.0
        ev = self._iterator(wav, return_seconds=False)
        if not ev:
            return []
        return self._event_to_segments(ev)

    def flush(self) -> SpeechSegment | None:
        """Close an open speech region at end of stream."""
        if not self._iterator.triggered:
            return None
        end = self._iterator.current_sample
        start = max(0, end - self._iterator.speech_pad_samples)
        self._iterator.reset_states()
        return SpeechSegment(
            start_sample=int(start),
            end_sample=int(end),
            sample_rate=self.sample_rate,
        )

    def _event_to_segments(self, ev: dict) -> list[SpeechSegment]:
        if ev.get("end") is not None:
            return [
                SpeechSegment(
                    start_sample=int(ev["start"]),
                    end_sample=int(ev["end"]),
                    sample_rate=self.sample_rate,
                )
            ]
        return []

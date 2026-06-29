#!/usr/bin/env python3
"""M1 D2: Silero VAD smoke — record mic or use synthetic tone."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.metrics import LatencyTracker  # noqa: E402
from voice.vad import CHUNK_SAMPLES_16K, SileroVAD  # noqa: E402


def _synthetic_speech_wav(sr: int, seconds: float = 2.0) -> np.ndarray:
    """Tone burst as stand-in when no mic / quiet room."""
    t = np.linspace(0, seconds, int(sr * seconds), dtype=np.float32)
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    pad = np.zeros(int(sr * 0.5), dtype=np.float32)
    audio = np.concatenate([pad, tone, pad])
    return (audio * 32767).astype(np.int16)


def _record_mic(seconds: float, sr: int, device: int | None) -> np.ndarray:
    import sounddevice as sd

    print(f"Recording {seconds}s @ {sr} Hz — speak now...")
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="int16", device=device)
    sd.wait()
    return audio[:, 0]


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 VAD smoke test")
    parser.add_argument(
        "--mic",
        action="store_true",
        help="Record from microphone instead of synthetic tone",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Record duration (default from voice.yaml)",
    )
    args = parser.parse_args()
    cfg = load_voice_config()
    vad_cfg = cfg["vad"]
    mic_cfg = cfg["mic"]
    sr = vad_cfg["sample_rate"]
    seconds = args.seconds or mic_cfg["record_seconds"]

    tracker = LatencyTracker()
    tracker.start("vad_load")
    vad = SileroVAD(
        sample_rate=sr,
        threshold=vad_cfg["threshold"],
        min_silence_ms=vad_cfg["min_silence_ms"],
        speech_pad_ms=vad_cfg.get("speech_pad_ms", 30),
    )
    print(f"[ok] Silero VAD loaded ({tracker.stop('vad_load'):.0f} ms)")

    if args.mic:
        pcm = _record_mic(seconds, sr, mic_cfg["device"])
    else:
        print("[info] Using synthetic tone (pass --mic to test real microphone)")
        pcm = _synthetic_speech_wav(sr, seconds=min(seconds, 2.0))

    segments: list = []
    tracker.start("vad_process")
    # Pad tail so last chunk is exactly 512 samples
    pad = (CHUNK_SAMPLES_16K - len(pcm) % CHUNK_SAMPLES_16K) % CHUNK_SAMPLES_16K
    if pad:
        pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])
    for i in range(0, len(pcm), CHUNK_SAMPLES_16K):
        chunk = pcm[i : i + CHUNK_SAMPLES_16K]
        for seg in vad.process_chunk(chunk):
            segments.append((seg.start_sample, seg.end_sample, seg.duration_ms))
    tail = vad.flush()
    if tail:
        segments.append((tail.start_sample, tail.end_sample, tail.duration_ms))
    tracker.stop("vad_process")

    print(f"\nAudio: {len(pcm) / sr:.2f}s, {len(pcm)} samples @ {sr} Hz")
    print(f"Speech segments detected: {len(segments)}")
    for idx, (s0, s1, dur_ms) in enumerate(segments, 1):
        print(f"  [{idx}] samples {s0}-{s1}  duration={dur_ms:.0f} ms")

    print("\nLatency summary:")
    print(tracker.summary())

    if not segments and not args.mic:
        print(
            "\n[warn] Synthetic tone may not trigger VAD; re-run with --mic and speak."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

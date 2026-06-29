#!/usr/bin/env python3
"""M1 D2+D3: Record mic → VAD segments → ASR each segment (no LLM)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.asr_router import ASRRouter  # noqa: E402
from voice.audio_io import record_mic, save_wav_16k_mono  # noqa: E402
from voice.metrics import LatencyTracker  # noqa: E402
from voice.vad import CHUNK_SAMPLES_16K, SileroVAD  # noqa: E402


def _collect_segments(vad: SileroVAD, pcm: np.ndarray) -> list[tuple[int, int]]:
    pad = (CHUNK_SAMPLES_16K - len(pcm) % CHUNK_SAMPLES_16K) % CHUNK_SAMPLES_16K
    if pad:
        pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])
    spans: list[tuple[int, int]] = []
    for i in range(0, len(pcm), CHUNK_SAMPLES_16K):
        for seg in vad.process_chunk(pcm[i : i + CHUNK_SAMPLES_16K]):
            spans.append((seg.start_sample, seg.end_sample))
    tail = vad.flush()
    if tail:
        spans.append((tail.start_sample, tail.end_sample))
    return spans, pcm


def main() -> int:
    parser = argparse.ArgumentParser(description="Mic → VAD → ASR loopback")
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()
    cfg = load_voice_config()
    sr = cfg["vad"]["sample_rate"]
    out_dir = Path("/tmp/agent_voice_smoke/mic_loop")
    out_dir.mkdir(parents=True, exist_ok=True)

    tracker = LatencyTracker()
    print(f"Recording {args.seconds}s — speak Chinese or English...")
    pcm = record_mic(args.seconds, sr, cfg["mic"].get("device"))
    save_wav_16k_mono(out_dir / "raw.wav", pcm)

    vad = SileroVAD(
        sample_rate=sr,
        threshold=cfg["vad"]["threshold"],
        min_silence_ms=cfg["vad"]["min_silence_ms"],
        speech_pad_ms=cfg["vad"].get("speech_pad_ms", 30),
    )
    spans, pcm = _collect_segments(vad, pcm)
    print(f"VAD segments: {len(spans)}")
    if not spans:
        print("[warn] no speech detected — speak louder/closer to mic")
        return 1

    asr_cfg = cfg.get("asr", {})
    router = ASRRouter(
        whisper_size=asr_cfg.get("whisper_size", "base"),
        funasr_model=asr_cfg.get("funasr_model", "paraformer-zh"),
        device=asr_cfg.get("device", "auto"),
    )

    for idx, (s0, s1) in enumerate(spans, 1):
        clip = pcm[s0:s1]
        if len(clip) < sr * 0.3:
            continue
        wav = out_dir / f"seg_{idx}.wav"
        save_wav_16k_mono(wav, clip)
        tracker.start("asr_seg")
        text, lang = router.transcribe(wav)
        ms = tracker.stop("asr_seg")
        print(f"  [{idx}] {lang} ({ms:.0f} ms): {text!r}")

    print("\nLatency summary:")
    print(tracker.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

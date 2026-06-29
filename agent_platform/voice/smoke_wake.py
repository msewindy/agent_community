#!/usr/bin/env python3
"""M1 D4: openWakeWord smoke — score frames from mic or TTS wav."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.audio_io import load_audio_16k_mono, record_mic  # noqa: E402
from voice.metrics import LatencyTracker  # noqa: E402
from voice.wake import OWW_FRAME_SAMPLES, WakeWordDetector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 wake word smoke test")
    parser.add_argument("--mic", action="store_true", help="Record 3s from microphone")
    parser.add_argument(
        "--wav",
        type=Path,
        default=None,
        help="Score an existing 16k wav (default: smoke_en.wav if present)",
    )
    args = parser.parse_args()
    cfg = load_voice_config()
    wake_cfg = cfg.get("wake", {})
    models = wake_cfg.get("models") or [wake_cfg.get("model", "alexa")]
    threshold = wake_cfg.get("threshold", 0.5)

    tracker = LatencyTracker()
    tracker.start("wake_load")
    detector = WakeWordDetector(models=models, threshold=threshold)
    print(f"[ok] openWakeWord models {detector.model_names} ({tracker.stop('wake_load'):.0f} ms)")

    if args.mic:
        sr = 16000
        print("Recording 3s — say something close to the default wake word (e.g. 'alexa')...")
        pcm = record_mic(3.0, sr, cfg["mic"].get("device"))
    else:
        wav = args.wav or Path("/tmp/agent_voice_smoke/asr_wav/smoke_en.wav")
        if not wav.exists():
            wav = Path("/tmp/agent_voice_smoke/smoke_en.mp3")
        if not wav.exists():
            print("[error] no audio; run smoke_tts/asr or pass --mic")
            return 1
        pcm, _ = load_audio_16k_mono(wav)

    pad = (OWW_FRAME_SAMPLES - len(pcm) % OWW_FRAME_SAMPLES) % OWW_FRAME_SAMPLES
    if pad:
        pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])

    max_score = 0.0
    hits_total = 0
    tracker.start("wake_score")
    for i in range(0, len(pcm), OWW_FRAME_SAMPLES):
        frame = pcm[i : i + OWW_FRAME_SAMPLES]
        for hit in detector.score_frame(frame):
            hits_total += 1
            max_score = max(max_score, hit.score)
            print(f"  hit {hit.model_name} score={hit.score:.3f}")
    tracker.stop("wake_score")

    print(f"\nFrames scored: {len(pcm) // OWW_FRAME_SAMPLES}, hits={hits_total}, max_score={max_score:.3f}")
    print("Latency summary:")
    print(tracker.summary())
    if hits_total == 0:
        print(
            "\n[info] No wake hits (expected unless audio contains wake word). "
            "Re-run with --mic and say 'alexa' clearly."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

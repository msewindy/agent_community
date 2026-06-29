#!/usr/bin/env python3
"""M1 D3: ASR smoke — transcribe TTS reference clips (zh/en)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.asr_router import ASRRouter  # noqa: E402
from voice.audio_io import load_audio_16k_mono, save_wav_16k_mono  # noqa: E402
from voice.metrics import LatencyTracker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 ASR smoke test")
    parser.add_argument(
        "--clips-dir",
        type=Path,
        default=Path("/tmp/agent_voice_smoke"),
        help="Directory with smoke_zh.mp3 / smoke_en.mp3 from smoke_tts",
    )
    args = parser.parse_args()
    cfg = load_voice_config()
    asr_cfg = cfg.get("asr", {})

    clips = [
        ("zh", args.clips_dir / "smoke_zh.mp3", "zh"),
        ("en", args.clips_dir / "smoke_en.mp3", "en"),
    ]

    router = ASRRouter(
        whisper_size=asr_cfg.get("whisper_size", "base"),
        funasr_model=asr_cfg.get("funasr_model", "paraformer-zh"),
        device=asr_cfg.get("device", "auto"),
    )

    tracker = LatencyTracker()
    out_dir = args.clips_dir / "asr_wav"
    out_dir.mkdir(parents=True, exist_ok=True)

    for label, mp3, hint_lang in clips:
        if not mp3.exists():
            print(f"[skip] missing {mp3} — run smoke_tts.py first")
            continue
        wav = out_dir / f"smoke_{label}.wav"
        pcm, _ = load_audio_16k_mono(mp3)
        save_wav_16k_mono(wav, pcm)

        tracker.start(f"asr_{label}")
        text, lang = router.transcribe(wav, language=hint_lang)
        ms = tracker.stop(f"asr_{label}")
        print(f"\n[{label}] hint={hint_lang} detected={lang} ({ms:.0f} ms)")
        print(f"  file: {wav}")
        print(f"  text: {text!r}")

    print("\nLatency summary:")
    print(tracker.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

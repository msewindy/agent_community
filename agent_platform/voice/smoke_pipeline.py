#!/usr/bin/env python3
"""M1 D7: End-to-end text or mic → Hermes → TTS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice.pipeline import VoicePipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice pipeline smoke")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--text", help="User message (skip ASR)")
    group.add_argument("--wav", type=Path, help="16k wav file")
    group.add_argument("--mic", action="store_true", help="Record from microphone")
    group.add_argument("--wake", action="store_true", help="Wait for wake word then mic turn")
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--no-play", action="store_true")
    parser.add_argument("--barge-in", action="store_true", help="Enable VAD interrupt during TTS")
    parser.add_argument("-l", "--language", default="zh")
    args = parser.parse_args()

    pipe = VoicePipeline()
    play = not args.no_play

    barge = args.barge_in or None

    if args.wake:
        result = pipe.run_wake_then_turn(play=play, barge_in=barge)
    elif args.text:
        result = pipe.run_text_turn(
            args.text, language=args.language, play=play, barge_in=barge
        )
    elif args.wav:
        result = pipe.run_audio_turn(args.wav, play=play, barge_in=barge)
    else:
        result = pipe.run_mic_turn(args.seconds, play=play, barge_in=barge)

    print(json.dumps({k: v for k, v in result.items() if k != "metrics"}, ensure_ascii=False, indent=2))
    print("\n--- metrics ---")
    print(result.get("metrics", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

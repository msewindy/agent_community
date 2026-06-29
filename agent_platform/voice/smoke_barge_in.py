#!/usr/bin/env python3
"""M1 D8: TTS playback + mic VAD barge-in demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.pipeline import VoicePipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Long reply TTS with barge-in; speak during playback to interrupt"
    )
    parser.add_argument(
        "-t",
        "--text",
        default="请用大约五句话介绍人工智能的发展历史，语速正常。",
        help="Prompt that yields a longer TTS reply",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="After barge-in, record 3s and run a second turn",
    )
    args = parser.parse_args()

    cfg = load_voice_config()
    cfg.setdefault("barge_in", {})["enabled"] = True
    pipe = VoicePipeline(cfg)

    print("[1] Sending to Hermes (may take several seconds)...")
    r1 = pipe.run_text_turn(args.text, play=True, barge_in=True)
    print(f"    barge_in={r1.get('barge_in')}")
    print(f"    reply preview: {r1['reply_text'][:120]}...")

    if r1.get("barge_in") and args.recover:
        print("\n[2] Barge-in detected — capture follow-up utterance...")
        r2 = pipe.run_barge_in_recovery(record_seconds=3.0)
        print(f"    asr: {r2.get('asr_text', '')!r}")
        print(f"    reply: {r2.get('reply_text', '')[:120]}...")
    elif not r1.get("barge_in"):
        print("\n[info] No barge-in during playback. Speak loudly during TTS and re-run.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

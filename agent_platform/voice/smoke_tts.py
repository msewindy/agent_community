#!/usr/bin/env python3
"""M1 D1: Edge-TTS smoke — zh + en MP3 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# platform/ on path → import voice.*
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.metrics import LatencyTracker  # noqa: E402
from voice.tts import synthesize_to_file_sync  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 TTS smoke test")
    parser.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=Path("/tmp/agent_voice_smoke"),
    )
    args = parser.parse_args()
    cfg = load_voice_config()
    tts_cfg = cfg["tts"]
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        ("zh", "你好，M1 语音管线 TTS 测试。", tts_cfg["zh_voice"]),
        ("en", "Hello, M1 voice pipeline TTS test.", tts_cfg["en_voice"]),
    ]

    tracker = LatencyTracker()
    for lang, text, voice in cases:
        path = out_dir / f"smoke_{lang}.mp3"
        tracker.start(f"tts_{lang}")
        synthesize_to_file_sync(text, path, voice=voice)
        ms = tracker.stop(f"tts_{lang}")
        print(f"[ok] {lang} -> {path} ({path.stat().st_size} bytes, {ms:.0f} ms)")

    print("\nLatency summary:")
    print(tracker.summary())
    print(f"\nPlay: ffplay -nodisp -autoexit {out_dir}/smoke_zh.mp3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

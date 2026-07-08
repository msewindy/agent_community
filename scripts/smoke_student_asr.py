#!/usr/bin/env python3
"""Smoke test — student chat DashScope ASR (WSL / local)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_platform.api.student_chat import _load_hermes_env  # noqa: E402

_load_hermes_env()

from agent_platform.voice.dashscope_asr import AsrError, transcribe_upload, transcribe_wav_file  # noqa: E402


def main() -> int:
    wav = Path("/tmp/asr_test_hello.wav")
    if not wav.is_file():
        print("FAIL: missing /tmp/asr_test_hello.wav (download sample first)", file=sys.stderr)
        return 1
    try:
        text = transcribe_wav_file(wav)
        print(f"OK wav: {text!r}")
    except AsrError as e:
        print(f"FAIL wav: {e}", file=sys.stderr)
        return 1

    # webm round-trip via ffmpeg
    webm = Path("/tmp/asr_test_hello.webm")
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-c:a", "libopus", str(webm)],
        check=True,
        capture_output=True,
    )
    try:
        text2 = transcribe_upload(webm.read_bytes(), filename="test.webm", content_type="audio/webm")
        print(f"OK webm: {text2!r}")
    except AsrError as e:
        print(f"FAIL webm: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

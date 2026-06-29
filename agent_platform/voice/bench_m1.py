#!/usr/bin/env python3
"""M1 D9: Latency benchmark — write stats to JSON + stdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.hermes_bridge import HermesBridge  # noqa: E402
from voice.metrics import LatencyTracker  # noqa: E402
from voice.tts import synthesize_to_file_sync, voice_for_language  # noqa: E402
from voice.vad import SileroVAD  # noqa: E402
from voice.wake import WakeWordDetector  # noqa: E402


def bench_vad_load(n: int, cfg: dict, tracker: LatencyTracker) -> None:
    vc = cfg["vad"]
    for _ in range(n):
        tracker.start("vad_load")
        SileroVAD(
            sample_rate=vc["sample_rate"],
            threshold=vc["threshold"],
            min_silence_ms=vc["min_silence_ms"],
            speech_pad_ms=vc.get("speech_pad_ms", 30),
        )
        tracker.stop("vad_load")


def bench_wake_load(n: int, cfg: dict, tracker: LatencyTracker) -> bool:
    try:
        wc = cfg.get("wake", {})
        models = wc.get("models") or [wc.get("model", "alexa")]
        for _ in range(n):
            tracker.start("wake_load")
            WakeWordDetector(models=models, threshold=wc.get("threshold", 0.5))
            tracker.stop("wake_load")
        return True
    except Exception as exc:
        print(f"[skip] wake_load: {exc}")
        return False


def bench_hermes(n: int, cfg: dict, tracker: LatencyTracker) -> None:
    hc = cfg["hermes"]
    bridge = HermesBridge(
        provider=hc.get("provider", "deepseek"),
        model=hc.get("model", "deepseek-chat"),
    )
    for i in range(n):
        tracker.start("hermes")
        bridge.ask(f"回复数字{i}，只要一个阿拉伯数字。")
        tracker.stop("hermes")


def bench_tts(n: int, cfg: dict, tracker: LatencyTracker) -> None:
    tts = cfg["tts"]
    voice = voice_for_language("zh", zh_voice=tts["zh_voice"], en_voice=tts["en_voice"])
    out = Path("/tmp/agent_voice_smoke/bench")
    out.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        tracker.start("tts")
        synthesize_to_file_sync(f"基准测试第{i}句。", out / f"bench_{i}.mp3", voice=voice)
        tracker.stop("tts")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vad-runs", type=int, default=20)
    parser.add_argument("--wake-runs", type=int, default=5)
    parser.add_argument("--hermes-runs", type=int, default=5)
    parser.add_argument("--tts-runs", type=int, default=10)
    parser.add_argument("-o", "--output", type=Path, default=Path("/tmp/agent_voice_bench.json"))
    parser.add_argument("--skip-hermes", action="store_true")
    args = parser.parse_args()

    cfg = load_voice_config()
    tracker = LatencyTracker()

    bench_vad_load(args.vad_runs, cfg, tracker)
    bench_wake_load(args.wake_runs, cfg, tracker)
    if not args.skip_hermes:
        bench_hermes(args.hermes_runs, cfg, tracker)
    bench_tts(args.tts_runs, cfg, tracker)

    stats = tracker.stats()
    payload = {
        "targets": {
            "wake_to_vad_ready_ms": 500,
            "asr_to_tts_first_ms": 1000,
        },
        "stats": stats,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("M1 benchmark results:")
    print(tracker.summary())
    print(f"\nwritten: {args.output}")

    vad_p50 = stats.get("vad_load", {}).get("p50", 0)
    print(f"\nM1.6 check: vad_load p50={vad_p50:.0f}ms (proxy for wake→VAD ready)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

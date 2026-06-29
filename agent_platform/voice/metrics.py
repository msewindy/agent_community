"""Simple latency tracking for M1 benchmarks."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = min(int(len(s) * p), len(s) - 1)
    return s[idx]


@dataclass
class LatencyTracker:
    """Record named phases; print summary on exit."""

    _starts: dict[str, float] = field(default_factory=dict)
    _durations_ms: dict[str, list[float]] = field(default_factory=dict)

    def start(self, name: str) -> None:
        self._starts[name] = time.perf_counter()

    def stop(self, name: str) -> float:
        t0 = self._starts.pop(name, None)
        if t0 is None:
            raise KeyError(f"no start for {name!r}")
        ms = (time.perf_counter() - t0) * 1000
        self._durations_ms.setdefault(name, []).append(ms)
        return ms

    def record(self, name: str, ms: float) -> None:
        self._durations_ms.setdefault(name, []).append(ms)

    def stats(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for name, samples in self._durations_ms.items():
            out[name] = {
                "n": len(samples),
                "p50": percentile(samples, 0.5),
                "p95": percentile(samples, 0.95),
                "min": min(samples),
                "max": max(samples),
            }
        return out

    def summary(self) -> str:
        lines = []
        for name, st in sorted(self.stats().items()):
            lines.append(
                f"  {name}: n={int(st['n'])} p50={st['p50']:.0f}ms p95={st['p95']:.0f}ms"
            )
        return "\n".join(lines) if lines else "  (no samples)"

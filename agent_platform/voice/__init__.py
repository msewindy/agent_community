"""M1 voice duplex: wake → VAD → ASR → Hermes → TTS."""

from agent_platform.voice.metrics import LatencyTracker

__all__ = ["LatencyTracker"]

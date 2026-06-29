"""Load platform/config/voice.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "voice.yaml"


def load_voice_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

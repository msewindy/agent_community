"""Load evolution.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_CFG_PATH = Path(__file__).resolve().parents[1] / "config" / "evolution.yaml"


@lru_cache(maxsize=1)
def load_evolution_config() -> dict:
    if not _CFG_PATH.is_file():
        return {}
    return yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8")) or {}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

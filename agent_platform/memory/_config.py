"""Load agent_platform/config/memory.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "memory.yaml"


def repo_root() -> Path:
    root = os.environ.get("AGENT_COMMUNITY_ROOT", "").strip()
    if root:
        return Path(root)
    return Path(__file__).resolve().parents[2]


def resolve_persist_path(cfg: dict) -> Path | None:
    """Resolve mock.persist_path relative to AGENT_COMMUNITY_ROOT / repo root."""
    mock_cfg = cfg.get("mock") or {}
    raw = mock_cfg.get("persist_path")
    if not raw:
        return None
    p = Path(str(raw))
    if p.is_absolute():
        return p
    return repo_root() / p


def load_memory_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

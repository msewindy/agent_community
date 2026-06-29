"""Load agent_platform/config/behavior.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "behavior.yaml"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_behavior_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_store_root(cfg: dict | None = None) -> Path:
    cfg = cfg or load_behavior_config()
    raw = (cfg.get("store") or {}).get("root", "behavior_data")
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def resolve_profile_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_behavior_config()
    root = resolve_store_root(cfg)
    name = (cfg.get("store") or {}).get("profile_file", "profile.yaml")
    return root / name

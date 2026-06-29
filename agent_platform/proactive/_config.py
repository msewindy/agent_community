"""Load agent_platform/config/proactive.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "proactive.yaml"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_proactive_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_store_root(cfg: dict | None = None) -> Path:
    cfg = cfg or load_proactive_config()
    raw = (cfg.get("store") or {}).get("root", "proactive_data")
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()

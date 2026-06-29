"""Load agent_platform/config/calibration.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "calibration.yaml"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_calibration_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_log_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_calibration_config()
    raw = (cfg.get("audit") or {}).get("log_path", "calibration_data/events.log.md")
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()

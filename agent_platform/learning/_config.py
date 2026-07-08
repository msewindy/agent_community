"""Load agent_platform/config/student_learning.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "student_learning.yaml"


def repo_root() -> Path:
    root = os.environ.get("AGENT_COMMUNITY_ROOT", "").strip()
    if root:
        return Path(root)
    return Path(__file__).resolve().parents[2]


def load_student_learning_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_data_root(cfg: dict | None = None) -> Path:
    env = os.environ.get("STUDENT_JARVIS_DATA_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    cfg = cfg or load_student_learning_config()
    raw = (cfg.get("data") or {}).get("root", "student_data")
    p = Path(str(raw))
    if not p.is_absolute():
        p = repo_root() / p
    return p.resolve()


def resolve_student_id(
    args: dict | None = None,
    kwargs: dict | None = None,
    cfg: dict | None = None,
) -> str | None:
    """Resolve student_id from tool args, env, or config default."""
    if args:
        raw = args.get("student_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    if kwargs:
        raw = kwargs.get("student_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    env = os.environ.get("STUDENT_JARVIS_STUDENT_ID", "").strip()
    if env:
        return env
    cfg = cfg or load_student_learning_config()
    default = (cfg.get("hermes") or {}).get("default_student_id")
    if default is not None and str(default).strip():
        return str(default).strip()
    return None

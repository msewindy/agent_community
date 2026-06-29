"""User policy switches for camera/mic (M4)."""

from __future__ import annotations

import json
from pathlib import Path

from agent_platform.perception.contracts import PerceptionPolicy, utc_now


def load_policy(path: Path, defaults: PerceptionPolicy) -> PerceptionPolicy:
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PerceptionPolicy(
            camera_enabled=bool(data.get("camera_enabled", defaults.camera_enabled)),
            microphone_enabled=bool(
                data.get("microphone_enabled", defaults.microphone_enabled)
            ),
            updated_at=utc_now(),
        )
    except (OSError, json.JSONDecodeError):
        return defaults


def save_policy(path: Path, policy: PerceptionPolicy) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "camera_enabled": policy.camera_enabled,
        "microphone_enabled": policy.microphone_enabled,
        "updated_at": policy.updated_at.isoformat(),
    }
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

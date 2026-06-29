"""Persist behavior profile to YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from agent_platform.behavior.contracts import BehaviorProfile, BehaviorProfileUpdate


class BehaviorStore:
    def __init__(self, profile_path: Path, default_profile: Optional[dict] = None) -> None:
        self._path = profile_path
        self._default = default_profile or {}

    def load(self) -> BehaviorProfile:
        if not self._path.is_file():
            return BehaviorProfile.model_validate(self._default)
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        merged = {**self._default, **raw}
        return BehaviorProfile.model_validate(merged)

    def save(self, profile: BehaviorProfile) -> BehaviorProfile:
        profile.touch()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = profile.model_dump(mode="json")
        self._path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return profile

    def update(self, patch: BehaviorProfileUpdate) -> BehaviorProfile:
        current = self.load()
        data = current.model_dump()
        for key, val in patch.model_dump(exclude_unset=True).items():
            if val is not None:
                data[key] = val
        updated = BehaviorProfile.model_validate(data)
        return self.save(updated)

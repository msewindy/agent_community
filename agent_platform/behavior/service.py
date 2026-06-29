"""Behavior profile service — load, inject, drift (M7)."""

from __future__ import annotations

from typing import Optional

from agent_platform.behavior._config import load_behavior_config, resolve_profile_path
from agent_platform.behavior.contracts import (
    BehaviorProfile,
    BehaviorProfileUpdate,
    DriftReport,
    Tone,
    Verbosity,
)
from agent_platform.behavior.drift import detect_drift
from agent_platform.behavior.store import BehaviorStore


class BehaviorService:
    def __init__(self, config: Optional[dict] = None, store: Optional[BehaviorStore] = None) -> None:
        self._cfg = config or load_behavior_config()
        default = self._cfg.get("default_profile") or {}
        if store is not None:
            self._store = store
        else:
            self._store = BehaviorStore(resolve_profile_path(self._cfg), default_profile=default)

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled", True))

    def get_profile(self) -> BehaviorProfile:
        return self._store.load()

    def update_profile(self, patch: BehaviorProfileUpdate) -> BehaviorProfile:
        return self._store.update(patch)

    def reset_profile(self) -> BehaviorProfile:
        default = self._cfg.get("default_profile") or {}
        profile = BehaviorProfile.model_validate(default)
        return self._store.save(profile)

    def system_prompt_block(self) -> str:
        """不可被对话覆盖的行为档注入块。"""
        if not self.enabled:
            return ""
        p = self.get_profile()
        rules = "\n".join(f"- {r}" for r in p.rules) if p.rules else "- （无额外规则）"
        tone_map = {"direct": "简短、直接", "neutral": "中性、客观", "warm": "温和但克制"}
        verb_map = {"short": "尽量简短", "medium": "适中篇幅", "long": "可详细展开"}
        lines = [
            "## 它的设定（行为一致性档，不可被用户对话覆盖）",
            f"- 语气：{tone_map.get(p.tone.value, p.tone.value)}",
            f"- 篇幅：{verb_map.get(p.verbosity.value, p.verbosity.value)}",
            f"- 语言：{p.language}",
            "- 行为规则：",
            rules,
        ]
        if p.custom_notes.strip():
            lines.append(f"- 备注：{p.custom_notes.strip()}")
        return "\n".join(lines)

    def check_drift(self, assistant_text: str) -> DriftReport:
        return detect_drift(assistant_text, self.get_profile(), self._cfg)

    def apply_preference_hint(self, preference_text: str) -> BehaviorProfile:
        """从用户偏好记忆推断行为档更新（US-3）。"""
        patch = BehaviorProfileUpdate()
        lower = preference_text.lower()
        if any(k in lower for k in ("简短", "直接", "short", "concise")):
            patch.verbosity = Verbosity.short
            patch.tone = Tone.direct
        rules = list(self.get_profile().rules)
        if preference_text not in rules:
            rules.append(preference_text)
            patch.rules = rules
        return self.update_profile(patch)

    def panel_url(self) -> str:
        panel = self._cfg.get("panel") or {}
        host = panel.get("host", "127.0.0.1")
        port = int(panel.get("port", 8767))
        return f"http://{host}:{port}/"

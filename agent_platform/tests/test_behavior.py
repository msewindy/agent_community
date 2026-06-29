"""Tests for M7 behavior profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.behavior.contracts import BehaviorProfileUpdate, Verbosity
from agent_platform.behavior.service import BehaviorService
from agent_platform.behavior.store import BehaviorStore


@pytest.fixture
def beh_svc(tmp_path: Path) -> BehaviorService:
    cfg = {
        "enabled": True,
        "default_profile": {
            "tone": "direct",
            "verbosity": "short",
            "rules": ["回复尽量简短直接"],
        },
        "store": {"root": str(tmp_path), "profile_file": "profile.yaml"},
        "drift": {"enabled": True, "threshold": 0.35, "max_chars_short": 100},
    }
    store = BehaviorStore(tmp_path / "profile.yaml", default_profile=cfg["default_profile"])
    return BehaviorService(config=cfg, store=store)


def test_system_prompt_block(beh_svc: BehaviorService) -> None:
    block = beh_svc.system_prompt_block()
    assert "它的设定" in block
    assert "简短" in block


def test_profile_persist(beh_svc: BehaviorService) -> None:
    beh_svc.update_profile(BehaviorProfileUpdate(rules=["规则A"]))
    reloaded = BehaviorService(
        config=beh_svc._cfg,
        store=BehaviorStore(
            Path(beh_svc._cfg["store"]["root"]) / "profile.yaml",
            default_profile=beh_svc._cfg["default_profile"],
        ),
    )
    assert "规则A" in reloaded.get_profile().rules


def test_drift_verbose(beh_svc: BehaviorService) -> None:
    text = "作为一个AI" + "x" * 200
    report = beh_svc.check_drift(text)
    assert report.drifted

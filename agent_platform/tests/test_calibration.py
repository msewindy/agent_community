"""Tests for M7 calibration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_platform.calibration.calibrator import calibrate_output
from agent_platform.calibration.contracts import CalibrateRequest, ConfidenceLevel, UserCorrectionRequest
from agent_platform.calibration.service import CalibrationService
from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.service import MemoryService


@pytest.fixture
def cal_cfg(tmp_path: Path) -> dict:
    return {
        "enabled": True,
        "confidence": {"high_threshold": 0.75, "low_threshold": 0.45},
        "low_confidence_prefix": "我不太确定，",
        "require_source_for": ["version"],
        "sensitive_patterns": {"version": r"v[\d.]+"},
        "apology": {"enabled": True, "template": "抱歉，更新为 {new_value}"},
        "audit": {"enabled": False, "log_path": str(tmp_path / "log.md")},
    }


def test_low_confidence_hedge(cal_cfg: dict) -> None:
    req = CalibrateRequest(text="版本 v0.2", confidence=0.9)
    out = calibrate_output(req, cal_cfg)
    assert out.confidence_level == ConfidenceLevel.low
    assert "不太确定" in out.text or "不确定" in out.text


def test_tool_source_keeps_answer(cal_cfg: dict) -> None:
    req = CalibrateRequest(text="查到了，版本 v0.2", has_tool_source=True)
    out = calibrate_output(req, cal_cfg)
    assert out.confidence_level != ConfidenceLevel.low


def test_correction_supersede(cal_cfg: dict) -> None:
    mem = MemoryService(adapter=MockMemAdapter(), config={"backend": "mock", "gate": {"enabled": False}})
    svc = CalibrationService(config=cal_cfg, memory_service=mem)
    rec = mem.write("版本 v0.1")
    result = svc.correct(
        UserCorrectionRequest(record_id=rec.record_id, old_value="v0.1", new_value="版本 v0.2")
    )
    assert result.success
    hits = mem.search("v0.2")
    assert hits.hits

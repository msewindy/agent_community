"""Tests for M8 US-8 and trace audit."""

from __future__ import annotations

from agent_platform.integration.trace_audit import accept_trace_chain
from agent_platform.integration.us8_project import accept_us8_project_recall


def test_us8_project_recall() -> None:
    assert accept_us8_project_recall()


def test_trace_chain() -> None:
    assert accept_trace_chain()

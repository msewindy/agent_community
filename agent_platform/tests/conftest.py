"""Shared fixtures for agent_platform memory tests."""

from __future__ import annotations

import pytest

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.service import MemoryService


@pytest.fixture
def mock_adapter() -> MockMemAdapter:
    return MockMemAdapter()


@pytest.fixture
def memory_service(mock_adapter: MockMemAdapter) -> MemoryService:
    return MemoryService(
        adapter=mock_adapter,
        config={
            "backend": "mock",
            "device": {"default_id": "test-device"},
            "gate": {"enabled": False},
        },
    )


@pytest.fixture
def device_id() -> str:
    return "test-device"

"""M4 D3 — VLM describe + policy gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.perception.contracts import DescribeRequest
from agent_platform.perception.frames import opencv_available
from agent_platform.perception.service import PerceptionService
from agent_platform.perception.vision_intent import is_vision_intent


def test_vision_intent():
    assert is_vision_intent("看下桌上那本书叫什么名字？")
    assert is_vision_intent("What book is on my desk?")
    assert not is_vision_intent("帮我写一段 Python")


@pytest.mark.skipif(not opencv_available(), reason="opencv not installed")
def test_describe_mock_us2(tmp_path: Path):
    root = tmp_path / "p"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root)},
        "policy": {"camera_enabled": True},
        "vision": {"enabled": True, "provider": "mock"},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    r = svc.describe(DescribeRequest(question="桌上那本书叫什么？"))
    assert r.allowed
    assert r.description
    assert "思考" in r.description or "Fast" in r.description
    assert (root / "visions").is_dir()


@pytest.mark.skipif(not opencv_available(), reason="opencv not installed")
def test_describe_camera_off(tmp_path: Path):
    root = tmp_path / "p"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root)},
        "policy": {"camera_enabled": False},
        "vision": {"enabled": True, "provider": "mock"},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    r = svc.describe(DescribeRequest(question="看看桌上有什么"))
    assert not r.allowed
    assert r.reason_code == "camera_disabled"


def test_vlm_openai_compatible_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from agent_platform.perception.adapters.vlm_openai import OpenAiCompatibleVlmAdapter

    img = tmp_path / "t.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "桌上是一本《思考，快与慢》。"}}],
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    monkeypatch.setattr(
        "agent_platform.perception.adapters.vlm_openai.httpx.Client",
        lambda **kw: mock_client,
    )

    vlm = OpenAiCompatibleVlmAdapter(
        base_url="https://example.com/v1",
        model="qwen-vl-max",
        api_key="test-key",
    )
    text = vlm.describe(img, "什么书？")
    assert "思考" in text


def test_describe_vision_disabled(tmp_path: Path):
    root = tmp_path / "p"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root)},
        "policy": {"camera_enabled": True},
        "vision": {"enabled": False},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    r = svc.describe(DescribeRequest(question="看下书"))
    assert not r.allowed
    assert r.reason_code == "vision_disabled"

"""VLM adapter factory + vision record store (M4 D3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from agent_platform.perception.adapters.vlm_mock import MockVlmAdapter
from agent_platform.perception.adapters.vlm_openai import OpenAiCompatibleVlmAdapter


@runtime_checkable
class VlmPort(Protocol):
    provider: str
    model: str

    def describe(self, image_path: Path, question: str) -> str: ...


def build_vlm_adapter(cfg: dict) -> VlmPort:
    v = cfg.get("vision") or {}
    provider = (v.get("provider") or "mock").lower()
    if provider == "openai_compatible":
        return OpenAiCompatibleVlmAdapter(
            base_url=str(v.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
            model=str(v.get("model", "qwen-vl-max")),
            api_key_env=str(v.get("api_key_env", "DASHSCOPE_API_KEY")),
            api_key=v.get("api_key"),
            timeout_s=float(v.get("timeout_s", 60)),
            max_tokens=int(v.get("max_tokens", 512)),
            system_prompt=v.get("system_prompt"),
        )
    return MockVlmAdapter()


def save_vision_record(
    store_root: Path,
    *,
    trace_id: str,
    question: str,
    description: str,
    model: str,
    provider: str,
    frame_path: str,
    latency_ms: int,
) -> Path:
    visions_dir = store_root / "visions"
    visions_dir.mkdir(parents=True, exist_ok=True)
    stem = trace_id.replace("/", "_")[:36]
    out = visions_dir / f"{stem}.json"
    record: dict[str, Any] = {
        "trace_id": trace_id,
        "question": question,
        "description": description,
        "model": model,
        "provider": provider,
        "frame_path": frame_path,
        "latency_ms": latency_ms,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out

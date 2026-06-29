"""OpenAI-compatible VLM — Qwen2-VL via DashScope / vLLM / OpenRouter (M4 D3)."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx


class OpenAiCompatibleVlmAdapter:
    """POST /chat/completions with image_url (base64 data URL)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "DASHSCOPE_API_KEY",
        api_key: str | None = None,
        timeout_s: float = 60.0,
        max_tokens: int = 512,
        system_prompt: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or (
            "你是共域陪伴助理的视觉模块。根据用户问题和图像，用简洁中文回答；"
            "看不清就说看不清，不要编造书名或物体。"
        )

    @property
    def provider(self) -> str:
        return "openai_compatible"

    def _resolve_api_key(self) -> str:
        key = (self._api_key or os.environ.get(self.api_key_env) or "").strip()
        if not key:
            raise RuntimeError(f"Missing API key env: {self.api_key_env}")
        return key

    @staticmethod
    def _image_data_url(path: Path) -> str:
        suffix = path.suffix.lower()
        mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
        raw = path.read_bytes()
        b64 = base64.standard_b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def describe(self, image_path: Path, question: str) -> str:
        if not image_path.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._resolve_api_key()}",
            "Content-Type": "application/json",
        }
        user_text = (question or "请描述这张图片中的主要内容。").strip()
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": self._image_data_url(image_path)},
                        },
                    ],
                },
            ],
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("VLM response missing choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            text = "".join(parts).strip()
        else:
            text = (content or "").strip()
        if not text:
            raise RuntimeError("VLM returned empty content")
        return text

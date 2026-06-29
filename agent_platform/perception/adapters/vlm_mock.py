"""Mock VLM — US-2 desk/book scenario without GPU or API (M4 D3)."""

from __future__ import annotations

from pathlib import Path


class MockVlmAdapter:
    provider = "mock"
    model = "mock-Qwen2-VL"

    def describe(self, image_path: Path, question: str) -> str:
        q = (question or "").strip()
        ql = q.lower()
        if any(k in q for k in ("书", "书名", "叫什么")) or "book" in ql:
            return (
                "我看到桌上有一本书，书名是《思考，快与慢》（Thinking, Fast and Slow），"
                "作者是丹尼尔·卡尼曼。需要我帮你做点什么吗？"
            )
        return (
            f"[mock Qwen2-VL] 已查看 {image_path.name}。"
            f"针对你的问题「{q or '描述画面'}」：画面为室内桌面场景（合成帧测试）。"
        )

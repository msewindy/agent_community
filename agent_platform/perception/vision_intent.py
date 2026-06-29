"""Vision intent heuristics — on-demand trigger only (M4 D3 / US-2)."""

from __future__ import annotations

# 中英混说常见视觉问法（非穷举；Hermes 也可直接调 describe 工具）
_VISION_TRIGGERS_ZH = (
    "看下",
    "看看",
    "瞧",
    "识别",
    "叫什么",
    "是什么书",
    "什么书",
    "书名",
    "桌上",
    "桌子上",
    "摄像头",
    "拍一下",
    "拍张",
    "眼前",
    "能看到",
)

_VISION_TRIGGERS_EN = (
    "look at",
    "what book",
    "see the",
    "on the desk",
    "on my desk",
    "what is on",
    "what's on",
    "identify",
    "read the title",
)


def is_vision_intent(text: str) -> bool:
    """True when user message likely needs a camera + VLM pass."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(k in t for k in _VISION_TRIGGERS_ZH):
        return True
    return any(k in t for k in _VISION_TRIGGERS_EN)

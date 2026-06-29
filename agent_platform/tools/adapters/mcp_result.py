"""Normalize MCP CallToolResult to Python values."""

from __future__ import annotations

import json
from typing import Any


def parse_call_tool_result(result: Any) -> Any:
    blocks = getattr(result, "content", None) or []
    texts: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text is not None:
            texts.append(str(text))
            continue
        data = getattr(block, "data", None)
        if data is not None:
            texts.append(str(data))

    if not texts:
        return {"isError": getattr(result, "isError", False)}

    if len(texts) == 1:
        raw = texts[0].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"text": raw}

    return {"text": "\n".join(texts)}

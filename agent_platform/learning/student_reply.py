"""面向学生的助手回复脱敏 — 剥离工具/框架用语，避免泄露给三年级孩子。"""

from __future__ import annotations

import re

# 段落级：含任一强信号即视为框架块（非口播内容）
_FRAMEWORK_BLOCK_SIGNALS: tuple[str, ...] = (
    "已经对齐",
    "不用切换",
    "无需切换",
    "already_current",
    "StudentContext",
    "learning_focus_set",
    "learning_catalog_lookup",
    "explain_kp",
    "questions_suggest",
    "push_queue_peek",
    "student_answer_gate",
    "持久单元",
    "持久情境",
    "写回持久",
    "工具契约",
    "catalog 闭集",
    "has_wiki",
    "description_text",
    "gap_id",
    "attempt_id",
    "unit_id",
    "本轮讲新课预检",
    "系统自动",
    "勿向学生复述",
    "勿向孩子复述",
    "场景行为档",
)

_TOOL_NAME_RE = re.compile(
    r"`(?:learning_[a-z_]+|explain_kp|student_[a-z_]+|gap_map_query|push_queue_peek)`",
    re.IGNORECASE,
)
_GAP_ID_INLINE_RE = re.compile(r"\bgap-[a-z0-9-]+\b")

# 整行删除（行首匹配，用于清理零散泄露）
_FRAMEWORK_LINE_RE = re.compile(
    r"^[\s>*•-]*("
    r"当前学科.*(?:对齐|一致|切换)"
    r"|(?:已经|已)(?:对齐|一致).*(?:不用|无需)切换"
    r"|向孩子.*StudentContext"
    r"|工具[：:].*learning_"
    r")\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_HRULE_SPLIT_RE = re.compile(r"\n-{3,}\s*\n+")


def _is_framework_block(block: str) -> bool:
    s = (block or "").strip()
    if not s:
        return False
    lower = s.lower()
    return any(sig.lower() in lower for sig in _FRAMEWORK_BLOCK_SIGNALS)


def sanitize_student_reply(text: str) -> str:
    """移除助手回复中的框架/工具说明，只保留面向孩子的对话正文。"""
    out = (text or "").strip()
    if not out:
        return out

    # 常见模式：框架前言 + --- + 真正回答
    parts = _HRULE_SPLIT_RE.split(out, maxsplit=1)
    if len(parts) == 2 and _is_framework_block(parts[0]):
        out = parts[1].strip()

    # 去掉开头连续的框架段落
    while out:
        chunks = re.split(r"\n\n+", out, maxsplit=1)
        if len(chunks) == 1:
            if _is_framework_block(chunks[0]):
                return ""
            break
        head, tail = chunks[0], chunks[1]
        if _is_framework_block(head):
            out = tail.strip()
        else:
            break

    out = _FRAMEWORK_LINE_RE.sub("", out)
    out = _TOOL_NAME_RE.sub("", out)
    out = _GAP_ID_INLINE_RE.sub("这方面", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

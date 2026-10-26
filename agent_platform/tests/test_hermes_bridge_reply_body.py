"""Hermes stdout → 学生可见正文：剥离运维状态行。"""

from __future__ import annotations

from agent_platform.voice.hermes_bridge import _reply_body


def test_reply_body_strips_self_improvement_and_session_id() -> None:
    stdout = (
        "好呀，我们学第二单元。\n"
        "💾 Self-improvement review: User profile updated\n"
        "session_id: abc-123\n"
    )
    body = _reply_body(stdout)
    assert body == "好呀，我们学第二单元。"
    assert "Self-improvement" not in body
    assert "session_id" not in body

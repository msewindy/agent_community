#!/usr/bin/env python3
"""M5 D4 smoke — VoiceProactiveBridge (no Hermes / TTS)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _proactive_svc(root: Path):
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService
    from agent_platform.proactive.service import ProactiveService

    cfg = {
        "enabled": True,
        "level": "L0",
        "quiet_hours": {"enabled": False},
        "triggers": {
            "work_break": {
                "enabled": True,
                "work_minutes_threshold": 120,
                "message": "已经 2 小时了，要不要休息一下？",
            }
        },
        "session": {"snooze_rest_of_session": True},
        "memory": {"write_dismiss_preference": True, "dedup_enabled": True},
        "store": {"root": str(root)},
    }
    mem = MemoryService(
        adapter=MockMemAdapter(),
        config={"backend": "mock", "gate": {"enabled": False}},
    )
    return ProactiveService(config=cfg, store_root=root, memory_service=mem)


def run_smoke() -> int:
    from agent_platform.voice.proactive_bridge import VoiceProactiveBridge

    with tempfile.TemporaryDirectory(prefix="voice-proactive-") as td:
        root = Path(td)
        svc = _proactive_svc(root)
        bridge = VoiceProactiveBridge(
            enabled=True,
            auto_feedback_on_dismiss=True,
            auto_parse_work_minutes=True,
            nudge_after_work_report=True,
            service=svc,
        )

        dismiss = bridge.on_user_message("别打扰我", session_id="vp-s1")
        if not dismiss.reply_override or "打扰" not in dismiss.reply_override:
            print(f"FAIL dismiss override: {dismiss}", file=sys.stderr)
            return 1
        print("dismiss → reply_override: OK")

        snoozed = bridge.maybe_proactive_nudge(session_id="vp-s1", work_minutes=130)
        if snoozed.proactive_allowed:
            print(f"FAIL should block after snooze: {snoozed}", file=sys.stderr)
            return 1
        print("post-dismiss nudge blocked: OK")

        work = bridge.on_user_message("我连续工作了2小时", session_id="vp-s2")
        if work.work_minutes_reported != 120.0:
            print(f"FAIL work parse: {work.work_minutes_reported}", file=sys.stderr)
            return 1
        if not work.reply_override or "休息" not in work.reply_override:
            print(f"FAIL nudge after work report: {work}", file=sys.stderr)
            return 1
        print("work report + nudge: OK")

        nudge = bridge.maybe_proactive_nudge(
            session_id="vp-s3", work_minutes=125, natural_pause=True
        )
        if not nudge.proactive_nudge or "休息" not in nudge.proactive_nudge:
            print(f"FAIL proactive nudge: {nudge}", file=sys.stderr)
            return 1
        print(f"agent-initiated nudge: OK — {nudge.proactive_nudge[:24]}…")

        empty = bridge.on_user_message("你好", session_id=None)
        if empty.handled:
            print("FAIL should skip without session_id", file=sys.stderr)
            return 1

        meta = bridge.turn_metadata(work)
        if not meta.get("proactive_work_minutes"):
            print(f"FAIL metadata {meta}", file=sys.stderr)
            return 1

        print("smoke_voice_proactive: PASS")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())

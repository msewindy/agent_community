#!/usr/bin/env python3
"""M5 D1 smoke — quiet hours + work_break + dismiss snooze."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService
    from agent_platform.proactive.contracts import ProactiveEvaluateRequest, ProactiveFeedbackRequest
    from agent_platform.proactive.service import ProactiveService

    with tempfile.TemporaryDirectory(prefix="proactive-d1-") as td:
        root = Path(td)
        cfg = {
            "enabled": True,
            "level": "L0",
            "quiet_hours": {"enabled": True, "start": "22:00", "end": "07:00", "timezone": "UTC"},
            "triggers": {
                "work_break": {
                    "enabled": True,
                    "work_minutes_threshold": 120,
                    "message": "已经 2 小时了，要不要休息一下？",
                }
            },
            "session": {"snooze_rest_of_session": True},
            "memory": {"write_dismiss_preference": True},
            "store": {"root": str(root)},
        }
        mem = MemoryService(
            adapter=MockMemAdapter(),
            config={"backend": "mock", "gate": {"enabled": False}},
        )
        svc = ProactiveService(config=cfg, store_root=root, memory_service=mem)

        # US-5 scene 3: quiet hours (23:00 UTC)
        q = svc.evaluate(
            ProactiveEvaluateRequest(
                session_id="s1",
                now=datetime(2026, 5, 20, 23, 0, tzinfo=ZoneInfo("UTC")),
            )
        )
        if q.allowed or q.reason_code != "quiet_hours":
            print(f"FAIL quiet hours: {q}", file=sys.stderr)
            return 1
        print("quiet_hours block: OK")

        # US-5 scene 1: work 2h → propose
        ok = svc.evaluate(
            ProactiveEvaluateRequest(session_id="s2", work_minutes=125, natural_pause=True)
        )
        if not ok.allowed or "休息" not in (ok.proposal.message if ok.proposal else ""):
            print(f"FAIL work_break: {ok}", file=sys.stderr)
            return 1
        print(f"work_break: OK — {ok.proposal.message}")

        # US-5 scene 2: dismiss → snooze + memory
        fb = svc.record_feedback(
            ProactiveFeedbackRequest(
                session_id="s2",
                user_message="我在做正事，别打扰",
            )
        )
        if not fb.session_snoozed:
            print("FAIL dismiss snooze", file=sys.stderr)
            return 1
        after = svc.evaluate(
            ProactiveEvaluateRequest(session_id="s2", work_minutes=200, natural_pause=True)
        )
        if after.allowed:
            print("FAIL should block after snooze", file=sys.stderr)
            return 1
        print("dismiss snooze: OK")

        print("smoke_proactive_d1: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

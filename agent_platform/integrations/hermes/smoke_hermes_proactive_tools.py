#!/usr/bin/env python3
"""Smoke Hermes proactive tool handlers (M5 D2)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from agent_platform.integrations.hermes import proactive_tools as pt  # noqa: E402


def main() -> int:
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService
    from agent_platform.proactive.service import ProactiveService

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = {
            "enabled": True,
            "quiet_hours": {"enabled": False},
            "triggers": {"work_break": {"enabled": True, "work_minutes_threshold": 120}},
            "session": {"snooze_rest_of_session": True},
            "memory": {"write_dismiss_preference": True, "dedup_enabled": True},
            "store": {"root": str(root)},
        }
        mem = MemoryService(
            adapter=MockMemAdapter(),
            config={"backend": "mock", "gate": {"enabled": False}},
        )
        svc = ProactiveService(config=cfg, store_root=root, memory_service=mem)
        pt._get_proactive_service = lambda: svc  # type: ignore[method-assign]

        st = json.loads(pt.agent_proactive_status({}, current_session_id="smoke-m5"))
        assert st.get("success") and st.get("enabled")

        ev = json.loads(
            pt.agent_proactive_evaluate(
                {"work_minutes": 130},
                current_session_id="smoke-m5",
            )
        )
        assert ev.get("allowed") and "休息" in (ev.get("proposal") or "")

        fb1 = json.loads(
            pt.agent_proactive_feedback(
                {"message": "我在做正事，别打扰"},
                current_session_id="smoke-m5",
            )
        )
        assert fb1.get("session_snoozed") and fb1.get("memory_written")

        fb2 = json.loads(
            pt.agent_proactive_feedback(
                {"message": "别打扰了"},
                current_session_id="smoke-m5",
            )
        )
        assert fb2.get("memory_deduped") or not fb2.get("memory_written")

        ev2 = json.loads(
            pt.agent_proactive_evaluate(
                {"work_minutes": 200},
                current_session_id="smoke-m5",
            )
        )
        assert not ev2.get("allowed") and ev2.get("reason_code") == "session_snoozed"

        rw = json.loads(
            pt.agent_proactive_report_work(
                {"work_minutes": 90},
                current_session_id="smoke-m5-2",
            )
        )
        assert rw.get("success") and rw.get("work_minutes_reported") == 90

    print("smoke_hermes_proactive_tools: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

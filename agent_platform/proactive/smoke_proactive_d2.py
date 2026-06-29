#!/usr/bin/env python3
"""M5 D2 smoke — memory dedup + Hermes tool path."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService
    from agent_platform.proactive.contracts import ProactiveFeedbackRequest
    from agent_platform.proactive.memory_feedback import DISMISS_SUBJECT_KEY
    from agent_platform.proactive.service import ProactiveService

    with tempfile.TemporaryDirectory(prefix="proactive-d2-") as td:
        root = Path(td)
        cfg = {
            "memory": {
                "write_dismiss_preference": True,
                "dedup_enabled": True,
                "dismiss_template": "用户不希望主动提醒",
            },
            "session": {"snooze_rest_of_session": True},
            "store": {"root": str(root)},
        }
        mem = MemoryService(
            adapter=MockMemAdapter(),
            config={"backend": "mock", "gate": {"enabled": False}},
        )
        svc = ProactiveService(config=cfg, store_root=root, memory_service=mem)

        r1 = svc.record_feedback(
            ProactiveFeedbackRequest(session_id="d2", user_message="别打扰")
        )
        if not r1.memory_written or not r1.memory_record_id:
            print(f"FAIL first write {r1}", file=sys.stderr)
            return 1

        dev = mem.default_device_id
        hits = mem.search("别打扰", device_id=dev, limit=5)
        if not hits.hits:
            print("FAIL search after write", file=sys.stderr)
            return 1
        meta = hits.hits[0].metadata or {}
        if meta.get("subject_key") != DISMISS_SUBJECT_KEY:
            print(f"FAIL subject_key {meta}", file=sys.stderr)
            return 1

        r2 = svc.record_feedback(
            ProactiveFeedbackRequest(session_id="d2b", user_message="不要打扰我")
        )
        if not r2.memory_deduped:
            print(f"FAIL dedup expected {r2}", file=sys.stderr)
            return 1

        print("memory_feedback dedup: OK")
        print("smoke_proactive_d2: PASS (run smoke_hermes_proactive_tools for Hermes path)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

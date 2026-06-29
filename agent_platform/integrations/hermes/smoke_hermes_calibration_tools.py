#!/usr/bin/env python3
"""Hermes smoke — M7 calibration + behavior tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agent_platform.integrations.hermes.calibration_tools import (  # noqa: E402
    agent_behavior_get_prompt,
    agent_behavior_status,
    agent_calibrate_output,
    agent_handle_correction,
    check_m7_available,
)
from agent_platform.integrations.hermes.tools import (  # noqa: E402
    agent_memory_write,
    bootstrap_agent_platform,
)


def main() -> int:
    bootstrap_agent_platform()
    if not check_m7_available():
        print("FAIL m7 not available", file=sys.stderr)
        return 1

    os.environ["AGENT_COMMUNITY_ROOT"] = str(_REPO)

    cal = json.loads(agent_calibrate_output({"text": "版本 v9.9", "confidence": 0.95}))
    if not cal.get("success") or cal.get("confidence_level") != "low":
        print(f"FAIL calibrate tool: {cal}", file=sys.stderr)
        return 1
    print("OK   agent_calibrate_output")

    st = json.loads(agent_behavior_status({}))
    if not st.get("success") or not st.get("panel_url"):
        print(f"FAIL behavior status: {st}", file=sys.stderr)
        return 1
    print("OK   agent_behavior_status")

    pr = json.loads(agent_behavior_get_prompt({}))
    if "它的设定" not in pr.get("system_prompt", ""):
        print(f"FAIL get_prompt: {pr}", file=sys.stderr)
        return 1
    print("OK   agent_behavior_get_prompt")

    wrote = json.loads(agent_memory_write({"content": "版本 v0.1", "category": "other", "kind": "fact"}))
    if not wrote.get("success"):
        print(f"FAIL memory write for correction test: {wrote}", file=sys.stderr)
        return 1

    corr = json.loads(
        agent_handle_correction(
            {
                "record_id": wrote["record_id"],
                "old_value": "v0.1",
                "new_value": "版本 v0.2",
            }
        )
    )
    if not corr.get("success") or "抱歉" not in corr.get("apology_text", ""):
        print(f"FAIL correction tool: {corr}", file=sys.stderr)
        return 1
    print("OK   agent_handle_correction")

    print("smoke_hermes_calibration_tools: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

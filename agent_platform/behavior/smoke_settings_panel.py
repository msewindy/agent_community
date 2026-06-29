#!/usr/bin/env python3
"""M7 settings panel smoke."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    from agent_platform.api.settings_panel import create_app
    from agent_platform.behavior.service import BehaviorService
    from agent_platform.behavior.store import BehaviorStore

    td = tempfile.mkdtemp(prefix="m7_panel_")
    root = Path(td)
    cfg = {
        "enabled": True,
        "default_profile": {
            "tone": "direct",
            "verbosity": "short",
            "language": "zh-CN",
            "rules": ["回复尽量简短直接"],
        },
        "store": {"root": str(root), "profile_file": "profile.yaml"},
        "drift": {"enabled": True},
        "panel": {"host": "127.0.0.1", "port": 8767},
    }
    store = BehaviorStore(root / "profile.yaml", default_profile=cfg["default_profile"])
    svc = BehaviorService(config=cfg, store=store)
    client = TestClient(create_app(config=cfg, service=svc))

    r = client.get("/health")
    if r.status_code != 200:
        print("FAIL health", file=sys.stderr)
        return 1

    get_p = client.get("/api/behavior/profile").json()
    if get_p["verbosity"] != "short":
        print(f"FAIL get profile: {get_p}", file=sys.stderr)
        return 1

    put_p = client.put(
        "/api/behavior/profile",
        json={"rules": ["用户偏好：直接简短"], "verbosity": "short", "tone": "direct"},
    ).json()
    if "直接简短" not in " ".join(put_p["rules"]):
        print(f"FAIL put profile: {put_p}", file=sys.stderr)
        return 1

    drift = client.post("/api/behavior/drift", json={"text": "作为一个AI很高兴为你" + "x" * 400}).json()
    if not drift.get("drifted"):
        print(f"FAIL drift api: {drift}", file=sys.stderr)
        return 1

    print("OK   settings panel GET/PUT/drift")
    print("smoke_settings_panel: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

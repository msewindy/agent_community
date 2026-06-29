#!/usr/bin/env python3
"""M2 D9 — automated acceptance for US-3 (cross-session recall) and US-7 (panel delete)."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tempfile
from pathlib import Path


def _tmp_file(name: str) -> Path:
    """Cross-platform temp file path (Windows has no /tmp)."""
    return Path(tempfile.gettempdir()) / name

from fastapi.testclient import TestClient

from agent_platform.api.memory_panel import create_app
from agent_platform.memory.adapters.memverse import MemVerseAdapter
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def accept_us3_mock(persist_path: Path, device_id: str) -> bool:
    """US-3: write → new process/service (restart) → search still hits."""
    cfg = {
        "backend": "mock",
        "device": {"default_id": device_id},
        "gate": {"enabled": True, "dedup": True},
        "audit": {"enabled": True, "db_path": str(persist_path.with_suffix(".audit.db"))},
        "mock": {"persist_path": str(persist_path)},
    }
    persist_path.unlink(missing_ok=True)

    svc1 = MemoryService(config=cfg)
    marker = "US3_ACCEPTANCE_SHORT_REPLIES"
    rec = svc1.write(
        f"{marker}：用户偏好回复尽量简短",
        device_id=device_id,
        category=MemoryCategory.preference,
        trace_id="us3-day1",
    )
    _ok(f"US-3 session1 write record_id={rec.record_id[:8]}…")

    # Simulate restart: new MemoryService, same on-disk mock store
    svc2 = MemoryService(config=cfg)
    res = svc2.search("简短", device_id=device_id, category=MemoryCategory.preference, trace_id="us3-day3")
    if not res.hits or not any(marker in h.content for h in res.hits):
        _fail(f"US-3 restart search: hits={len(res.hits)}")
        return False
    _ok(f"US-3 restart search hits={len(res.hits)} (preference persisted)")

    audit = svc2.audit_trace("us3-day3")
    if not any(e["event_type"] == "search" for e in audit):
        _fail("US-3 audit missing search event on day3")
        return False
    _ok("US-3 audit chain on recall trace")
    # Release SQLite handles before temp dir cleanup (Windows file lock).
    svc1._audit = None  # type: ignore[attr-defined]
    svc2._audit = None  # type: ignore[attr-defined]
    del svc1, svc2
    gc.collect()
    return True


def accept_us3_memverse(device_id: str) -> bool:
    """US-3 via MemVerse Docker (optional)."""
    ad = MemVerseAdapter("http://127.0.0.1:8000", timeout_s=180)
    if not ad.ping():
        _fail("US-3 memverse: container not reachable on :8000")
        return False

    cfg = {
        "backend": "memverse",
        "device": {"default_id": device_id},
        "gate": {"enabled": False},
        "audit": {"enabled": True, "db_path": str(_tmp_file("m2_us3_memverse_audit.db"))},
        "memverse": {"base_url": "http://127.0.0.1:8000", "timeout_s": 180},
    }
    marker = "US3_MEMVERSE_MARKER"
    svc1 = MemoryService(config=cfg)
    svc1.write(f"{marker} preference short replies", device_id=device_id, category=MemoryCategory.preference)

    svc2 = MemoryService(config=cfg)
    res = svc2.search(marker, device_id=device_id)
    if not res.hits and not (res.raw and "error" not in str(res.raw.get("final_answer", "")).lower()):
        _fail(f"US-3 memverse search weak: hits={len(res.hits)} raw={str(res.raw)[:200]}")
        return False
    _ok("US-3 memverse write+search (restart simulated)")
    return True


def accept_us7_panel(device_id: str) -> bool:
    """US-7: panel list → delete → list empty → search miss."""
    cfg = {
        "backend": "mock",
        "device": {"default_id": device_id},
        "gate": {"enabled": False},
        "audit": {"enabled": True, "db_path": str(_tmp_file("m2_us7_panel_audit.db"))},
        "panel": {"force_mock_backend": True, "enable_audit": True},
    }
    svc = MemoryService(config=cfg)
    svc.write("健康：每日跑步", device_id=device_id, category=MemoryCategory.user_profile, subject_key="health.run")
    svc.write("偏好：简短", device_id=device_id, category=MemoryCategory.preference)

    client = TestClient(create_app(config=cfg, service=svc))

    health = client.get("/api/memories", params={"device_id": device_id, "category": "user_profile"}).json()
    if len(health) != 1:
        _fail(f"US-7 list filter: expected 1 health row, got {len(health)}")
        return False
    _ok("US-7 panel list + category filter")

    rid = health[0]["record_id"]
    del_r = client.delete(f"/api/memories/{rid}")
    if del_r.status_code != 200:
        _fail(f"US-7 delete HTTP {del_r.status_code}")
        return False

    after = client.get("/api/memories", params={"device_id": device_id, "category": "user_profile"}).json()
    if after:
        _fail("US-7 list still shows deleted record")
        return False

    res = svc.search("跑步", device_id=device_id)
    if any("跑步" in h.content for h in res.hits):
        _fail("US-7 search still returns deleted content")
        return False

    pref = svc.search("简短", device_id=device_id)
    if not pref.hits:
        _fail("US-7 unrelated preference should remain")
        return False

    _ok("US-7 delete tombstone + search respects deletion")
    return True


def accept_hermes_tools(device_id: str) -> bool:
    """US-3 path via Hermes tool handlers (same-process)."""
    import agent_platform.integrations.hermes.tools as ht

    cfg = {
        "backend": "mock",
        "device": {"default_id": device_id},
        "gate": {"enabled": False},
        "audit": {"enabled": False},
        "mock": {"persist_path": str(_tmp_file("m2_us_hermes_tools_store.json"))},
    }
    Path(cfg["mock"]["persist_path"]).unlink(missing_ok=True)
    svc = MemoryService(config=cfg)
    ht._get_service = lambda: svc  # type: ignore[attr-defined]

    w = json.loads(ht.agent_memory_write({"content": "Hermes路径：喜欢简短", "category": "preference"}))
    if not w.get("success"):
        _fail(f"hermes write: {w}")
        return False

    svc2 = MemoryService(config=cfg)
    ht._get_service = lambda: svc2  # type: ignore[attr-defined]
    s = json.loads(ht.agent_memory_search({"query": "简短"}))
    if not s.get("count"):
        _fail(f"hermes search after restart: {s}")
        return False
    _ok("US-3 Hermes tool write → restart → search")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="M2 US-3 / US-7 acceptance")
    p.add_argument("--memverse", action="store_true", help="also run US-3 against MemVerse Docker")
    p.add_argument("--device", default="us-acceptance-device")
    args = p.parse_args()

    ok = True
    td = Path(tempfile.mkdtemp(prefix="m2_us_"))
    try:
        persist = td / "mock_store.json"
        if not accept_us3_mock(persist, args.device):
            ok = False
    finally:
        gc.collect()
        import shutil

        shutil.rmtree(td, ignore_errors=True)
    if not accept_us7_panel(args.device):
        ok = False
    if not accept_hermes_tools(args.device):
        ok = False
    if args.memverse:
        if not accept_us3_memverse(args.device):
            ok = False

    print()
    if ok:
        print("accept_m2_us: PASS — US-3 + US-7 automated checks OK")
        print("Manual (recommended): hermes chat → ask agent to remember preference → restart hermes → ask again")
        return 0
    print("accept_m2_us: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

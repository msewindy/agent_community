"""US-8 — cross-session project status recall (C1 + B6)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService


def accept_us8_project_recall(device_id: str = "us8-device") -> bool:
    """Write project milestone → restart → search recalls ProjectX state."""
    td = tempfile.mkdtemp(prefix="m8_us8_")
    persist = Path(td) / "mem.json"
    cfg = {
        "backend": "mock",
        "device": {"default_id": device_id},
        "gate": {"enabled": False},
        "audit": {"enabled": True, "db_path": str(Path(td) / "audit.db")},
        "mock": {"persist_path": str(persist)},
    }

    marker_m1 = "milestone-1 完成"
    marker_m2 = "milestone-2 目标 6 月初出原型"
    content = f"ProjectX：{marker_m1}；下一步 {marker_m2}。"

    svc1 = MemoryService(config=cfg)
    rec = svc1.write(
        content,
        device_id=device_id,
        category=MemoryCategory.project,
        subject_key="project.ProjectX",
        trace_id="us8-week1",
        metadata={"project": "ProjectX", "device_scope": device_id},
    )

    svc2 = MemoryService(config=cfg)
    hits = svc2.search("ProjectX", device_id=device_id, category=MemoryCategory.project, trace_id="us8-week2")
    if not hits.hits:
        return False
    blob = " ".join(h.content for h in hits.hits)
    if marker_m1 not in blob or marker_m2 not in blob:
        return False
    if rec.record_id not in {h.record_id for h in hits.hits}:
        return False

    audit = svc2.audit_trace("us8-week2")
    if not any(e.get("event_type") == "search" for e in audit):
        return False
    return True

"""M2 D7 — FastAPI memory panel (US-7: browse / filter / delete)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from agent_platform.memory._config import load_memory_config
from agent_platform.memory.contracts import MemoryCategory, MemoryStatus
from agent_platform.memory.service import MemoryService
from agent_platform.memory.trace import new_trace_id

_PANEL_HTML = (Path(__file__).parent / "templates" / "memory_panel.html").read_text(encoding="utf-8")


class MemoryRecordOut(BaseModel):
    record_id: str
    device_id: str
    ts: str
    category: str
    kind: str
    content: str
    status: str
    content_hash: Optional[str] = None
    trace_id: Optional[str] = None


class DeleteRequest(BaseModel):
    reason: str = Field(default="user_delete_panel")


def _record_to_out(rec) -> MemoryRecordOut:
    return MemoryRecordOut(
        record_id=rec.record_id,
        device_id=rec.device_id,
        ts=rec.ts.isoformat(),
        category=rec.category.value,
        kind=rec.kind.value,
        content=rec.content,
        status=rec.status.value,
        content_hash=rec.content_hash,
        trace_id=rec.trace_id,
    )


def create_app(config: Optional[dict] = None, service: Optional[MemoryService] = None) -> FastAPI:
    cfg = config or load_memory_config()
    # 面板默认 mock，便于 US-7 列表/删除；MemVerse 无 list API
    panel_cfg = cfg.get("panel") or {}
    if panel_cfg.get("force_mock_backend", True):
        # 保留 mock.persist_path，与 Hermes/CLI 共用落盘文件
        cfg = {**cfg, "backend": "mock", "mock": dict(cfg.get("mock") or {})}
    if panel_cfg.get("enable_audit", True):
        cfg.setdefault("audit", {})["enabled"] = True

    svc = service or MemoryService(config=cfg)
    backend = (cfg.get("backend") or "mock").lower()

    app = FastAPI(title="Agent Memory Panel", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "backend": backend}

    @app.get("/", response_class=HTMLResponse)
    def panel_page() -> str:
        return _PANEL_HTML.replace("{{BACKEND}}", backend)

    @app.get("/api/memories", response_model=list[MemoryRecordOut])
    def list_memories(
        device_id: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        include_tombstoned: bool = Query(False),
        limit: int = Query(100, ge=1, le=500),
    ) -> list[MemoryRecordOut]:
        cat = MemoryCategory(category) if category else None
        if include_tombstoned and hasattr(svc._adapter, "all_records"):
            rows = svc._adapter.all_records(include_tombstoned=True)  # type: ignore[attr-defined]
            if device_id:
                rows = [r for r in rows if r.device_id == device_id]
            if cat:
                rows = [r for r in rows if r.category == cat]
            rows = [r for r in rows if r.status == MemoryStatus.active or include_tombstoned]
            rows = rows[:limit]
        else:
            rows = svc.list_records(device_id=device_id, category=cat, limit=limit)

        return [_record_to_out(r) for r in rows]

    @app.delete("/api/memories/{record_id}")
    def delete_memory(record_id: str, body: DeleteRequest | None = None) -> MemoryRecordOut:
        reason = (body.reason if body else None) or "user_delete_panel"
        try:
            tomb = svc.delete(record_id, reason=reason, trace_id=new_trace_id())
        except KeyError:
            raise HTTPException(status_code=404, detail="record not found") from None
        return _record_to_out(tomb)

    @app.get("/api/audit/{trace_id}")
    def audit_trace(trace_id: str) -> list[dict[str, Any]]:
        rows = svc.audit_trace(trace_id)
        if not rows:
            raise HTTPException(status_code=404, detail="trace not found or audit disabled")
        return rows

    return app


app = create_app()


def main() -> None:
    import uvicorn

    cfg = load_memory_config()
    panel = cfg.get("panel") or {}
    host = panel.get("host", "127.0.0.1")
    port = int(panel.get("port", 8765))
    uvicorn.run("agent_platform.api.memory_panel:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

"""M6 D4 — FastAPI draft confirmation panel (L2 tool approve/reject)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent_platform.tools._config import load_mcp_config
from agent_platform.tools.contracts import (
    DraftApproveRequest,
    DraftRejectRequest,
    ToolInvokeStatus,
)
from agent_platform.tools.service import ToolService

_PANEL_HTML = (Path(__file__).parent / "templates" / "draft_panel.html").read_text(encoding="utf-8")


class DraftOut(BaseModel):
    draft_id: str
    session_id: str
    trace_id: str
    server: str
    tool: str
    arguments: dict[str, Any]
    level: str
    status: str
    preview: str
    created_at: str
    expires_at: Optional[str] = None


class RejectBody(BaseModel):
    reason: str = Field(default="")


class ApproveResultOut(BaseModel):
    draft_id: str
    status: str
    level: str
    message: str
    output: Any = None


def _draft_to_out(rec) -> DraftOut:
    level = rec.level.value if hasattr(rec.level, "value") else rec.level
    status = rec.status.value if hasattr(rec.status, "value") else rec.status
    return DraftOut(
        draft_id=rec.draft_id,
        session_id=rec.session_id,
        trace_id=rec.trace_id,
        server=rec.server,
        tool=rec.tool,
        arguments=rec.arguments,
        level=str(level),
        status=str(status),
        preview=rec.preview,
        created_at=rec.created_at.isoformat(),
        expires_at=rec.expires_at.isoformat() if rec.expires_at else None,
    )


def _panel_tool_config(cfg: dict) -> dict:
    """Panel smoke / dev: avoid spawning stdio MCP subprocesses."""
    panel = cfg.get("panel") or {}
    if not panel.get("force_mock_transports", False):
        return cfg
    servers = {}
    for name, sc in (cfg.get("servers") or {}).items():
        merged = dict(sc or {})
        merged["transport"] = "mock"
        servers[name] = merged
    return {**cfg, "servers": servers}


def create_app(config: Optional[dict] = None, service: Optional[ToolService] = None) -> FastAPI:
    cfg = _panel_tool_config(config or load_mcp_config())
    svc = service or ToolService(config=cfg)
    panel_cfg = cfg.get("panel") or {}

    app = FastAPI(title="Agent Tool Draft Panel", version="0.1.0")

    @app.on_event("shutdown")
    def _shutdown() -> None:
        svc.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        st = svc.status()
        return {
            "status": "ok",
            "sandbox_root": str(st.get("sandbox_root", "")),
            "draft_gate": str(st.get("draft_gate", True)),
        }

    @app.get("/", response_class=HTMLResponse)
    def panel_page() -> str:
        port = int(panel_cfg.get("port", 8766))
        return _PANEL_HTML.replace("{{PORT}}", str(port))

    @app.get("/api/drafts", response_model=list[DraftOut])
    def list_drafts(session_id: Optional[str] = Query(None)) -> list[DraftOut]:
        pending = svc.list_pending_drafts(session_id)
        return [_draft_to_out(d) for d in pending]

    @app.get("/api/drafts/{draft_id}", response_model=DraftOut)
    def get_draft(draft_id: str) -> DraftOut:
        from agent_platform.tools.draft_gate import load_draft

        rec = load_draft(svc._layout.drafts_dir, draft_id)  # noqa: SLF001
        if rec is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return _draft_to_out(rec)

    @app.post("/api/drafts/{draft_id}/approve", response_model=ApproveResultOut)
    def approve_draft(draft_id: str) -> ApproveResultOut:
        try:
            result = svc.approve_draft(DraftApproveRequest(draft_id=draft_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="draft not found") from None
        except (PermissionError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        st = result.status.value if hasattr(result.status, "value") else result.status
        lv = result.level.value if hasattr(result.level, "value") else result.level
        if st == ToolInvokeStatus.error.value:
            raise HTTPException(status_code=500, detail=result.message)
        return ApproveResultOut(
            draft_id=draft_id,
            status=str(st),
            level=str(lv),
            message=result.message,
            output=result.output,
        )

    @app.post("/api/drafts/{draft_id}/reject", response_model=DraftOut)
    def reject_draft(draft_id: str, body: RejectBody | None = None) -> DraftOut:
        reason = (body.reason if body else None) or ""
        try:
            rec = svc.reject_draft(DraftRejectRequest(draft_id=draft_id, reason=reason))
        except KeyError:
            raise HTTPException(status_code=404, detail="draft not found") from None
        return _draft_to_out(rec)

    @app.get("/api/status")
    def tool_status() -> dict[str, Any]:
        return svc.status()

    return app


def main() -> None:
    import uvicorn

    cfg = load_mcp_config()
    panel = cfg.get("panel") or {}
    host = panel.get("host", "127.0.0.1")
    port = int(panel.get("port", 8766))
    uvicorn.run(create_app(), host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

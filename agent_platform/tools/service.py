"""tool_service facade — governance + draft gate + MCP invoke (M6)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_platform.tools._config import load_mcp_config
from agent_platform.tools.adapters.router import McpRouterAdapter
from agent_platform.tools.contracts import (
    DraftApproveRequest,
    DraftRecord,
    DraftRejectRequest,
    DraftStatus,
    ToolInvokeRequest,
    ToolInvokeResult,
    ToolInvokeStatus,
    ToolLevel,
)
from agent_platform.tools.draft_gate import (
    approve_draft,
    create_draft,
    list_pending,
    load_draft,
    reject_draft,
)
from agent_platform.tools.governance import requires_draft, resolve_tool_level
from agent_platform.tools.store import append_event_log, ensure_store


class ToolService:
    def __init__(
        self,
        config: Optional[dict] = None,
        store_root: Optional[Path] = None,
        sandbox_root: Optional[Path] = None,
    ) -> None:
        self._cfg = config or load_mcp_config()
        self._layout = ensure_store(store_root, sandbox_root)
        self._adapter = McpRouterAdapter(self._cfg, self._layout.sandbox_root)
        gov = self._cfg.get("governance") or {}
        self._level_map = {str(k): str(v) for k, v in (gov.get("tool_levels") or {}).items()}
        self._default_level = str(gov.get("default_level", "L1"))
        dg = self._cfg.get("draft_gate") or {}
        self._draft_enabled = bool(dg.get("enabled", True))
        self._draft_ttl = float(dg.get("ttl_hours", 48))

    @property
    def store_root(self) -> Path:
        return self._layout.root

    @property
    def sandbox_root(self) -> Path:
        return self._layout.sandbox_root

    def close(self) -> None:
        self._adapter.close()

    def status(self) -> dict:
        transports = getattr(self._adapter, "server_transports", lambda: {})()
        return {
            "enabled": bool(self._cfg.get("enabled", True)),
            "sandbox_root": str(self._layout.sandbox_root),
            "draft_gate": self._draft_enabled,
            "servers": {
                name: bool((cfg or {}).get("enabled", False))
                for name, cfg in (self._cfg.get("servers") or {}).items()
            },
            "transports": transports,
            "tools": self._adapter.list_tools(),
        }

    def _level(self, req: ToolInvokeRequest) -> ToolLevel:
        return resolve_tool_level(
            req.server,
            req.tool,
            req.arguments,
            level_map=self._level_map,
            default_level=self._default_level,
        )

    def _execute(self, req: ToolInvokeRequest) -> ToolInvokeResult:
        level = self._level(req)
        try:
            output = self._adapter.invoke(req.server, req.tool, req.arguments)
        except Exception as e:
            append_event_log(
                self._layout,
                f"error {req.server}.{req.tool} trace={req.trace_id} {e}",
            )
            return ToolInvokeResult(
                status=ToolInvokeStatus.error,
                level=level,
                server=req.server,
                tool=req.tool,
                message=str(e),
                trace_id=req.trace_id,
            )
        append_event_log(
            self._layout,
            f"executed {req.server}.{req.tool} level={level.value} trace={req.trace_id}",
        )
        return ToolInvokeResult(
            status=ToolInvokeStatus.executed,
            level=level,
            server=req.server,
            tool=req.tool,
            output=output,
            message="ok",
            trace_id=req.trace_id,
        )

    def invoke(self, req: ToolInvokeRequest) -> ToolInvokeResult:
        if not bool(self._cfg.get("enabled", True)):
            return ToolInvokeResult(
                status=ToolInvokeStatus.denied,
                level=ToolLevel.L0,
                server=req.server,
                tool=req.tool,
                message="tools disabled in config",
                trace_id=req.trace_id,
            )

        level = self._level(req)

        if req.draft_id:
            draft = load_draft(self._layout.drafts_dir, req.draft_id)
            if draft is None:
                return ToolInvokeResult(
                    status=ToolInvokeStatus.error,
                    level=level,
                    server=req.server,
                    tool=req.tool,
                    message=f"draft not found: {req.draft_id}",
                    trace_id=req.trace_id,
                )
            if draft.status != DraftStatus.approved and not req.force_execute:
                return ToolInvokeResult(
                    status=ToolInvokeStatus.denied,
                    level=level,
                    server=req.server,
                    tool=req.tool,
                    draft_id=req.draft_id,
                    message=f"draft status={draft.status}, approve first",
                    trace_id=req.trace_id,
                )
            req = ToolInvokeRequest(
                server=draft.server,
                tool=draft.tool,
                arguments=draft.arguments,
                session_id=draft.session_id,
                trace_id=req.trace_id,
                draft_id=req.draft_id,
                force_execute=True,
            )
            return self._execute(req)

        if requires_draft(level, draft_enabled=self._draft_enabled) and not req.force_execute:
            draft = create_draft(
                self._layout.drafts_dir,
                req,
                level=level,
                ttl_hours=self._draft_ttl,
            )
            append_event_log(
                self._layout,
                f"draft_pending {draft.draft_id} {draft.server}.{draft.tool} trace={req.trace_id}",
            )
            return ToolInvokeResult(
                status=ToolInvokeStatus.draft_pending,
                level=level,
                server=req.server,
                tool=req.tool,
                draft_id=draft.draft_id,
                output={"preview": draft.preview},
                message="L2 action requires draft approval",
                trace_id=req.trace_id,
            )

        return self._execute(req)

    def approve_draft(self, req: DraftApproveRequest) -> ToolInvokeResult:
        draft = approve_draft(self._layout.drafts_dir, req)
        append_event_log(
            self._layout,
            f"draft_approved {draft.draft_id} trace={req.trace_id}",
        )
        return self.invoke(
            ToolInvokeRequest(
                server=draft.server,
                tool=draft.tool,
                arguments=draft.arguments,
                session_id=draft.session_id,
                trace_id=req.trace_id,
                draft_id=draft.draft_id,
                force_execute=True,
            )
        )

    def reject_draft(self, req: DraftRejectRequest) -> DraftRecord:
        rec = reject_draft(self._layout.drafts_dir, req)
        append_event_log(self._layout, f"draft_rejected {rec.draft_id}")
        return rec

    def list_pending_drafts(self, session_id: Optional[str] = None) -> list[DraftRecord]:
        return list_pending(self._layout.drafts_dir, session_id)

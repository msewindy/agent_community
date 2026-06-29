"""L2 draft confirmation gate (M6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from agent_platform.memory.contracts import utc_now
from agent_platform.tools.contracts import (
    DraftApproveRequest,
    DraftRecord,
    DraftRejectRequest,
    DraftStatus,
    ToolInvokeRequest,
    ToolLevel,
)


def _draft_path(drafts_dir: Path, draft_id: str) -> Path:
    safe = draft_id.replace("/", "_").replace("..", "_")[:64]
    return drafts_dir / f"{safe}.json"


def build_preview(server: str, tool: str, arguments: dict) -> str:
    args_preview = json.dumps(arguments, ensure_ascii=False)[:400]
    return f"{server}.{tool}({args_preview})"


def create_draft(
    drafts_dir: Path,
    req: ToolInvokeRequest,
    *,
    level: ToolLevel,
    ttl_hours: float = 48,
) -> DraftRecord:
    drafts_dir.mkdir(parents=True, exist_ok=True)
    rec = DraftRecord(
        session_id=req.session_id,
        trace_id=req.trace_id,
        server=req.server,
        tool=req.tool,
        arguments=req.arguments,
        level=level,
        preview=build_preview(req.server, req.tool, req.arguments),
    )
    payload = rec.model_dump(mode="json")
    payload["expires_at"] = (utc_now() + timedelta(hours=ttl_hours)).isoformat()
    _draft_path(drafts_dir, rec.draft_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rec


def load_draft(drafts_dir: Path, draft_id: str) -> Optional[DraftRecord]:
    path = _draft_path(drafts_dir, draft_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return DraftRecord.model_validate(data)


def _save_draft(drafts_dir: Path, rec: DraftRecord) -> None:
    payload = rec.model_dump(mode="json")
    _draft_path(drafts_dir, rec.draft_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def approve_draft(drafts_dir: Path, req: DraftApproveRequest) -> DraftRecord:
    rec = load_draft(drafts_dir, req.draft_id)
    if rec is None:
        raise KeyError(f"draft not found: {req.draft_id}")
    if rec.status != DraftStatus.pending:
        raise ValueError(f"draft not pending: {rec.status}")
    if req.session_id and req.session_id != rec.session_id:
        raise PermissionError("session_id mismatch for draft approval")
    rec.status = DraftStatus.approved
    rec.resolved_at = utc_now()
    _save_draft(drafts_dir, rec)
    return rec


def reject_draft(drafts_dir: Path, req: DraftRejectRequest) -> DraftRecord:
    rec = load_draft(drafts_dir, req.draft_id)
    if rec is None:
        raise KeyError(f"draft not found: {req.draft_id}")
    rec.status = DraftStatus.rejected
    rec.resolved_at = utc_now()
    _save_draft(drafts_dir, rec)
    return rec


def list_pending(drafts_dir: Path, session_id: Optional[str] = None) -> list[DraftRecord]:
    out: list[DraftRecord] = []
    if not drafts_dir.is_dir():
        return out
    for path in sorted(drafts_dir.glob("*.json")):
        try:
            rec = DraftRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if rec.status != DraftStatus.pending:
            continue
        if session_id and rec.session_id != session_id:
            continue
        out.append(rec)
    return out

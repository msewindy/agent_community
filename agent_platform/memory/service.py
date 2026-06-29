"""memory_service facade — sole business entry for memory I/O."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional
from uuid import uuid4

from agent_platform.memory._config import load_memory_config, resolve_persist_path
from agent_platform.memory.adapters.memverse import MemVerseAdapter
from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.audit import AuditConfig, AuditEvent, AuditStore, load_audit_config
from agent_platform.memory.contracts import (
    MemoryCategory,
    MemoryCorrectRequest,
    MemoryKind,
    MemoryPort,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryWriteRequest,
    ObserveEvent,
)
from agent_platform.memory.gate import (
    apply_write_metadata,
    content_hash,
    evaluate_write,
    load_gate_config,
)
from agent_platform.memory.trace import new_trace_id


def _build_adapter(cfg: dict) -> MemoryPort:
    backend = (cfg.get("backend") or "mock").lower()
    if backend == "memverse":
        return MemVerseAdapter.from_config(cfg)
    persist = resolve_persist_path(cfg)
    return MockMemAdapter(persist_path=persist) if persist else MockMemAdapter()


class MemoryService:
    def __init__(
        self,
        adapter: Optional[MemoryPort] = None,
        config: Optional[dict] = None,
        audit_store: Optional[AuditStore] = None,
    ) -> None:
        self._cfg = config or load_memory_config()
        self._adapter = adapter or _build_adapter(self._cfg)
        self._gate_cfg = load_gate_config(self._cfg)
        self._audit_cfg = load_audit_config(self._cfg)
        self._gate_index: list[MemoryRecord] = []
        if audit_store is not None:
            self._audit = audit_store
        elif self._audit_cfg.enabled:
            self._audit = AuditStore(self._audit_cfg.db_path)
        else:
            self._audit = None

    @property
    def gate_enabled(self) -> bool:
        return self._gate_cfg.enabled

    @property
    def audit_enabled(self) -> bool:
        return self._audit is not None

    @property
    def default_device_id(self) -> str:
        return (self._cfg.get("device") or {}).get("default_id", "default-device")

    def _log(
        self,
        trace_id: str,
        event_type: str,
        outcome: str,
        *,
        device_id: Optional[str] = None,
        record_id: Optional[str] = None,
        reason_code: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self._audit:
            return
        self._audit.append(
            AuditEvent(
                trace_id=trace_id,
                event_type=event_type,
                outcome=outcome,
                device_id=device_id,
                record_id=record_id,
                reason_code=reason_code,
                payload=payload or {},
            )
        )

    def audit_trace(self, trace_id: str) -> list[dict[str, Any]]:
        if not self._audit:
            return []
        return self._audit.list_by_trace(trace_id)

    def _existing_for_gate(self, device_id: str) -> list[MemoryRecord]:
        adapter_rows = self._adapter.list_records(device_id=device_id, limit=500)
        by_id = {r.record_id: r for r in adapter_rows}
        for r in self._gate_index:
            if r.device_id == device_id and r.record_id not in by_id:
                by_id[r.record_id] = r
        return list(by_id.values())

    def _run_gate(self, req: MemoryWriteRequest) -> MemoryWriteRequest:
        decision = evaluate_write(
            req,
            enabled=self._gate_cfg.enabled,
            existing=self._existing_for_gate(req.device_id),
            config=self._gate_cfg,
        )
        self._log(
            req.trace_id or "unknown",
            "gate_evaluate",
            "ok" if decision.allowed else "rejected",
            device_id=req.device_id,
            reason_code=decision.reason_code,
            payload={"details": decision.details, "content_preview": req.content[:200]},
        )
        if not decision.allowed:
            raise PermissionError(f"gate rejected write: {decision.reason_code}")
        return apply_write_metadata(req, decision)

    def write(
        self,
        content: str,
        *,
        device_id: Optional[str] = None,
        category=None,
        kind=None,
        trace_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        subject_key: Optional[str] = None,
        **kwargs,
    ) -> MemoryRecord:
        tid = trace_id or new_trace_id()
        metadata = dict(kwargs.get("metadata") or {})
        if subject_key:
            metadata["subject_key"] = subject_key

        req = MemoryWriteRequest(
            content=content,
            device_id=device_id or self.default_device_id,
            category=category or MemoryCategory.other,
            kind=kind or MemoryKind.fact,
            trace_id=tid,
            source_event_id=source_event_id,
            confidence=float(kwargs.get("confidence", 1.0)),
            metadata=metadata,
        )
        self._log(
            tid,
            "write_request",
            "ok",
            device_id=req.device_id,
            payload={"category": req.category.value, "kind": req.kind.value},
        )
        try:
            req = self._run_gate(req)
            record = self._adapter.write(req)
        except PermissionError:
            raise
        except Exception as e:
            self._log(tid, "write", "error", device_id=req.device_id, reason_code=type(e).__name__, payload={"error": str(e)})
            raise

        if not record.content_hash:
            record.content_hash = content_hash(record.content)
        if req.metadata:
            record.metadata = {**record.metadata, **req.metadata}
        record.trace_id = tid
        self._gate_index.append(record)
        self._log(
            tid,
            "write",
            "ok",
            device_id=record.device_id,
            record_id=record.record_id,
            reason_code=req.metadata.get("gate_reason_code"),
            payload={"content_hash": record.content_hash},
        )
        return record

    def write_observe(self, event: ObserveEvent, **kwargs) -> MemoryRecord:
        device_id = kwargs.get("device_id") or event.device_id or self.default_device_id
        self._log(
            event.trace_id,
            "observe_ingest",
            "ok",
            device_id=device_id,
            payload={"event_id": event.event_id, "source": event.source.value},
        )
        req = event.to_write_request(device_id=device_id)
        req.trace_id = event.trace_id
        try:
            req = self._run_gate(req)
            record = self._adapter.write(req)
        except Exception as e:
            self._log(event.trace_id, "write_observe", "error", device_id=device_id, payload={"error": str(e)})
            raise
        record.trace_id = event.trace_id
        self._gate_index.append(record)
        self._log(
            event.trace_id,
            "write_observe",
            "ok",
            device_id=device_id,
            record_id=record.record_id,
        )
        return record

    def search(
        self,
        query: str,
        *,
        device_id: Optional[str] = None,
        category=None,
        limit: int = 10,
        trace_id: Optional[str] = None,
    ) -> MemorySearchResult:
        tid = trace_id or new_trace_id()
        req = MemorySearchRequest(
            query=query,
            device_id=device_id or self.default_device_id,
            category=category,
            limit=limit,
            trace_id=tid,
        )
        try:
            result = self._adapter.search(req)
        except Exception as e:
            self._log(tid, "search", "error", device_id=req.device_id, payload={"query": query, "error": str(e)})
            raise
        self._log(
            tid,
            "search",
            "ok",
            device_id=req.device_id,
            payload={"query": query, "hit_count": len(result.hits)},
        )
        return result

    def correct(self, req: MemoryCorrectRequest) -> MemoryRecord:
        tid = req.trace_id or new_trace_id()
        self._log(
            tid,
            "correct_request",
            "ok",
            record_id=req.record_id,
            payload={"reason": req.reason, "has_replacement": req.replacement is not None},
        )
        try:
            record = self._adapter.correct(req)
        except Exception as e:
            self._log(tid, "correct", "error", record_id=req.record_id, payload={"error": str(e)})
            raise
        record.trace_id = tid
        self._gate_index.append(record)
        self._log(tid, "correct", "ok", record_id=record.record_id, payload={"reason": req.reason})
        return record

    def delete(
        self,
        record_id: str,
        *,
        reason: str = "user_delete_panel",
        trace_id: Optional[str] = None,
    ) -> MemoryRecord:
        """US-7：用户从面板删除 → tombstone（经 correct，无 replacement）。"""
        return self.correct(
            MemoryCorrectRequest(record_id=record_id, reason=reason, trace_id=trace_id)
        )

    def list_records(self, **kwargs):
        return self._adapter.list_records(**kwargs)


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    return MemoryService()

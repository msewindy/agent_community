"""Append-only audit store for memory pipeline — trace_id correlation (M2 D6)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AuditConfig:
    enabled: bool = False
    db_path: str = "/tmp/agent_platform_audit.db"


def load_audit_config(cfg: dict) -> AuditConfig:
    a = cfg.get("audit") or {}
    return AuditConfig(
        enabled=bool(a.get("enabled", False)),
        db_path=str(a.get("db_path", "/tmp/agent_platform_audit.db")),
    )


@dataclass
class AuditEvent:
    trace_id: str
    event_type: str
    outcome: str  # ok | rejected | error
    component: str = "memory_service"
    device_id: Optional[str] = None
    record_id: Optional[str] = None
    reason_code: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=utc_now_iso)


class AuditStore:
    """SQLite append-only audit log."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        trace_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        component TEXT NOT NULL,
        outcome TEXT NOT NULL,
        device_id TEXT,
        record_id TEXT,
        reason_code TEXT,
        payload_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit_events(trace_id);
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts);
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    def append(self, event: AuditEvent) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_events
                (ts, trace_id, event_type, component, outcome, device_id, record_id, reason_code, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.ts,
                    event.trace_id,
                    event.event_type,
                    event.component,
                    event.outcome,
                    event.device_id,
                    event.record_id,
                    event.reason_code,
                    json.dumps(event.payload, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_by_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_events
                WHERE trace_id = ?
                ORDER BY id ASC
                """,
                (trace_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in reversed(rows)]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = row["payload_json"]
    return {
        "id": row["id"],
        "ts": row["ts"],
        "trace_id": row["trace_id"],
        "event_type": row["event_type"],
        "component": row["component"],
        "outcome": row["outcome"],
        "device_id": row["device_id"],
        "record_id": row["record_id"],
        "reason_code": row["reason_code"],
        "payload": json.loads(payload) if payload else {},
    }

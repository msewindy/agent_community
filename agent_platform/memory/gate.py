"""Product gate for memory writes — M2 D5 MVP (dedup, conflict, sensitive)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from agent_platform.memory.contracts import GateDecision, MemoryRecord, MemoryStatus, MemoryWriteRequest


def content_hash(content: str) -> str:
    normalized = " ".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class GateConfig:
    enabled: bool = False
    dedup: bool = True
    conflict_check: bool = True
    sensitive_keywords: list[str] = field(default_factory=list)
    min_confidence: float = 0.0


def load_gate_config(cfg: dict) -> GateConfig:
    g = cfg.get("gate") or {}
    keywords = g.get("sensitive_keywords") or []
    return GateConfig(
        enabled=bool(g.get("enabled", False)),
        dedup=bool(g.get("dedup", True)),
        conflict_check=bool(g.get("conflict_check", True)),
        sensitive_keywords=[str(k).lower() for k in keywords],
        min_confidence=float(g.get("min_confidence", 0.0)),
    )


def subject_key(req: MemoryWriteRequest) -> str:
    """Stable key for conflict detection within a device."""
    if sk := req.metadata.get("subject_key"):
        return str(sk).strip()
    return f"{req.category.value}:{req.kind.value}"


def _active_records(existing: list[MemoryRecord], device_id: str) -> list[MemoryRecord]:
    return [
        r
        for r in existing
        if r.status == MemoryStatus.active and r.device_id == device_id
    ]


def evaluate_write(
    req: MemoryWriteRequest,
    *,
    enabled: bool = False,
    existing: Optional[list[MemoryRecord]] = None,
    config: Optional[GateConfig] = None,
) -> GateDecision:
    if not enabled:
        return GateDecision(allowed=True, reason_code="gate_disabled")

    cfg = config or GateConfig(enabled=True)
    existing = existing or []
    device_id = req.device_id
    digest = content_hash(req.content)
    rows = _active_records(existing, device_id)
    sk = subject_key(req)

    if req.confidence < cfg.min_confidence:
        return GateDecision(
            allowed=False,
            reason_code="low_confidence",
            details={"confidence": req.confidence, "min": cfg.min_confidence},
        )

    for kw in cfg.sensitive_keywords:
        if kw and kw in req.content.lower():
            return GateDecision(
                allowed=False,
                reason_code="sensitive_keyword",
                details={"keyword": kw},
            )

    if cfg.dedup:
        for rec in rows:
            if rec.content_hash == digest:
                return GateDecision(
                    allowed=False,
                    reason_code="duplicate",
                    details={"existing_record_id": rec.record_id, "content_hash": digest},
                )

    if cfg.conflict_check:
        for rec in rows:
            rec_sk = rec.metadata.get("subject_key") or f"{rec.category.value}:{rec.kind.value}"
            if rec_sk == sk and rec.content_hash != digest:
                return GateDecision(
                    allowed=False,
                    reason_code="conflict",
                    details={
                        "subject_key": sk,
                        "existing_record_id": rec.record_id,
                        "existing_preview": rec.content[:120],
                    },
                )

    return GateDecision(
        allowed=True,
        reason_code="ok",
        details={"content_hash": digest, "subject_key": sk},
    )


def apply_write_metadata(req: MemoryWriteRequest, decision: GateDecision) -> MemoryWriteRequest:
    """Inject gate provenance + subject_key into record metadata."""
    meta = dict(req.metadata)
    meta.setdefault("subject_key", subject_key(req))
    meta["content_hash"] = content_hash(req.content)
    meta["gate_reason_code"] = decision.reason_code
    if "source_tier" not in meta:
        meta["source_tier"] = meta.get("source_tier", "user_explicit")
    return req.model_copy(update={"metadata": meta})

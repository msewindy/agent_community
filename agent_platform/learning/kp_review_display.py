"""Web review display helpers — 中文对比视图 (P1-C)."""

from __future__ import annotations

from typing import Any, Optional

from agent_platform.learning.kp_catalog_diff import (
    CatalogDiff,
    ConflictKind,
    KpChangeKind,
    UnitChangeKind,
)
from agent_platform.learning.kp_ingest_review import (
    ConflictResolutionEntry,
    ResolutionAction,
    allowed_actions_for_conflict,
)

ACTION_LABELS: dict[str, str] = {
    ResolutionAction.use_draft.value: "采用文档内容",
    ResolutionAction.use_catalog.value: "保留知识库现有",
    ResolutionAction.skip.value: "跳过",
    ResolutionAction.rename_draft.value: "重命名后写入",
}

CONFLICT_KIND_LABELS: dict[str, str] = {
    ConflictKind.unit_exists.value: "单元已存在",
    ConflictKind.kp_title_mismatch.value: "知识点标题不一致",
    ConflictKind.kp_missing_in_draft.value: "文档未列出已有知识点",
    ConflictKind.kp_cross_unit.value: "知识点归属其他单元",
    ConflictKind.subject_grade_mismatch.value: "学科年级提示",
}

KP_CHANGE_LABELS: dict[str, str] = {
    KpChangeKind.new.value: "新增知识点",
    KpChangeKind.unchanged.value: "已存在（完全一致）",
    KpChangeKind.title_changed.value: "已存在（内容不同）",
    KpChangeKind.missing_in_draft.value: "知识库中有、文档未列出",
}


def action_labels_for(actions: list[str]) -> dict[str, str]:
    return {action: ACTION_LABELS.get(action, action) for action in actions}


def build_document_tree(parsed_draft: dict) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for unit in parsed_draft.get("units") or []:
        kps = [
            {
                "knowledge_point_id": kp.get("knowledge_point_id"),
                "title": kp.get("title"),
                "description": kp.get("description"),
            }
            for kp in unit.get("knowledge_points") or []
        ]
        units.append(
            {
                "unit_id": unit.get("unit_id"),
                "unit_title": unit.get("unit_title"),
                "textbook_chapter": unit.get("textbook_chapter"),
                "unit_description": unit.get("unit_description"),
                "knowledge_points": kps,
            }
        )
    return units


def _conflict_map(conflicts: list) -> dict[str, Any]:
    by_id: dict[str, Any] = {}
    for conflict in conflicts:
        if hasattr(conflict, "conflict_id"):
            by_id[conflict.conflict_id] = conflict
        else:
            by_id[conflict["conflict_id"]] = conflict
    return by_id


def _conflict_for_kp(conflicts_by_id: dict[str, Any], kp_id: str, unit_id: str) -> Optional[Any]:
    for key in (f"kp-title:{kp_id}", f"kp-cross:{kp_id}", f"kp-missing:{unit_id}:{kp_id}"):
        if key in conflicts_by_id:
            return conflicts_by_id[key]
    return None


def _kp_item(
    unit: Any,
    kp: Any,
    conflicts_by_id: dict[str, Any],
    res_by_id: dict[str, ConflictResolutionEntry],
) -> dict[str, Any]:
    conflict = _conflict_for_kp(conflicts_by_id, kp.knowledge_point_id, unit.unit_id)
    conflict_id = conflict.conflict_id if conflict and hasattr(conflict, "conflict_id") else (
        conflict.get("conflict_id") if conflict else None
    )
    kind = conflict.kind.value if conflict and hasattr(conflict, "kind") else (
        conflict.get("kind") if conflict else None
    )
    allowed = allowed_actions_for_conflict(conflict.kind) if conflict and hasattr(conflict, "kind") else (
        allowed_actions_for_conflict(ConflictKind(kind)) if kind else []
    )
    resolved = res_by_id.get(conflict_id) if conflict_id else None

    return {
        "unit_id": unit.unit_id,
        "unit_title": unit.draft_title,
        "knowledge_point_id": kp.knowledge_point_id,
        "draft_title": kp.draft_title,
        "catalog_title": kp.catalog_title,
        "change": kp.change.value,
        "change_label": KP_CHANGE_LABELS.get(kp.change.value, kp.change.value),
        "conflict_id": conflict_id,
        "kind_label": CONFLICT_KIND_LABELS.get(kind, "") if kind else "",
        "allowed_actions": allowed,
        "action_labels": action_labels_for(allowed),
        "resolution": resolved.model_dump(mode="json") if resolved else None,
        "blocking": bool(conflict_id and kind != ConflictKind.subject_grade_mismatch.value),
    }


def build_kb_comparison(
    catalog_diff: CatalogDiff,
    resolutions: list[ConflictResolutionEntry],
) -> dict[str, Any]:
    res_by_id = {r.conflict_id: r for r in resolutions}
    conflicts_by_id = _conflict_map(catalog_diff.conflicts)

    new_units: list[dict[str, Any]] = []
    unit_notes: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {
        "new": [],
        "identical": [],
        "different": [],
        "catalog_only": [],
    }

    for unit in catalog_diff.units:
        if unit.change == UnitChangeKind.new_unit:
            kps = []
            for kp in unit.knowledge_points:
                item = _kp_item(unit, kp, conflicts_by_id, res_by_id)
                kps.append(
                    {
                        "knowledge_point_id": item["knowledge_point_id"],
                        "title": item["draft_title"],
                        "conflict_id": item["conflict_id"],
                        "kind_label": item["kind_label"],
                        "allowed_actions": item["allowed_actions"],
                        "action_labels": item["action_labels"],
                        "resolution": item["resolution"],
                        "blocking": item["blocking"],
                    }
                )
            new_units.append(
                {
                    "unit_id": unit.unit_id,
                    "unit_title": unit.draft_title,
                    "knowledge_points": kps,
                }
            )
            continue

        if unit.catalog_title and unit.draft_title != unit.catalog_title:
            unit_notes.append(
                {
                    "unit_id": unit.unit_id,
                    "catalog_title": unit.catalog_title,
                    "draft_title": unit.draft_title,
                    "note": "单元名称不一致，入库时将采用文档中的名称",
                }
            )

        for kp in unit.knowledge_points:
            item = _kp_item(unit, kp, conflicts_by_id, res_by_id)
            if kp.change == KpChangeKind.new:
                groups["new"].append(item)
            elif kp.change == KpChangeKind.unchanged:
                groups["identical"].append(item)
            elif kp.change == KpChangeKind.title_changed:
                groups["different"].append(item)
            elif kp.change == KpChangeKind.missing_in_draft:
                groups["catalog_only"].append(item)

    group_labels = {
        "new": "新增知识点",
        "identical": "已存在（完全一致）",
        "different": "已存在（内容不同）",
        "catalog_only": "知识库中有、文档未列出",
    }

    return {
        "new_units": new_units,
        "unit_notes": unit_notes,
        "groups": [
            {"key": key, "label": group_labels[key], "items": groups[key]}
            for key in ("new", "identical", "different", "catalog_only")
            if groups[key]
        ],
    }


def localize_conflict(conflict: dict, resolution: Optional[dict]) -> dict:
    kind = conflict.get("kind", "")
    payload = dict(conflict)
    payload["kind_label"] = CONFLICT_KIND_LABELS.get(kind, kind)
    allowed = payload.get("allowed_actions") or []
    payload["action_labels"] = action_labels_for(allowed)
    if resolution:
        action = resolution.get("action")
        payload["resolution_label"] = ACTION_LABELS.get(action, action)
    return payload

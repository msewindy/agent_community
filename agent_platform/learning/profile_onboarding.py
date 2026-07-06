"""L1 — profile warmup orchestration (when to guide, welcome copy, stage transitions)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, resolve_data_root
from agent_platform.learning.contracts import PipelineStage, StudentContextPatch, utc_now
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.store import layout_for
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.student_identity import (
    _extract_name_from_text,
    memory_device_for_student,
    resolve_student_display_name,
)
from agent_platform.memory.profile_completeness import (
    ProfileSnapshot,
    assess_profile,
    extract_grade_label_from_text,
    extract_interest_phrase_from_text,
)
from agent_platform.memory.assistant_identity import (
    ASSISTANT_ALIAS_SUBJECT_KEY,
    DEFAULT_ASSISTANT_NAME,
    assistant_alias_memory_content,
    resolve_assistant_display_name,
)


_MISSING_LABELS = {
    "name": "怎么称呼",
    "grade": "年级是否准确",
    "interest": "一个爱好或喜欢的事",
}


def snapshot_for_student(
    student_id: str,
    *,
    cfg: Optional[dict] = None,
    data_root: Optional[Path] = None,
    memory_svc=None,
) -> ProfileSnapshot:
    cfg = cfg or load_student_learning_config()
    root = data_root or resolve_data_root(cfg)
    ctx_svc = StudentContextService(cfg, data_root=root)
    grade_ctx = None
    onboard_name = None
    onboard_grade = None
    lay = layout_for(student_id, root)
    if lay.profile_path.is_file():
        try:
            raw = json.loads(lay.profile_path.read_text(encoding="utf-8"))
            onboard_name = (raw.get("preferred_name") or "").strip() or None
            onboard_grade = (raw.get("grade") or "").strip() or None
        except Exception:
            pass
    if ctx_svc.exists(student_id):
        try:
            ctx = ctx_svc.get(student_id)
            grade_ctx = ctx.curriculum.grade
        except Exception:
            pass

    profiles = (cfg.get("students") or {}).get("profiles") or {}
    device_id = (profiles.get(student_id) or {}).get("memory_device_id")

    snap = assess_profile(
        memory_svc=memory_svc,
        device_id=device_id,
        onboarding_grade=onboard_grade,
        context_grade=grade_ctx,
        onboarding_preferred_name=onboard_name,
    )
    if not snap.display_name and ctx_svc.exists(student_id):
        try:
            name = resolve_student_display_name(
                student_id,
                cfg,
                ctx=ctx_svc.get(student_id),
                memory_svc=memory_svc,
                data_root=root,
            )
            if name and name != student_id:
                snap.display_name = name
                snap.has_display_name = True
                if "name" in snap.missing:
                    snap.missing = [m for m in snap.missing if m != "name"]
        except Exception:
            pass
    return snap


def assistant_name_for_student(
    student_id: str,
    *,
    cfg: Optional[dict] = None,
    memory_svc=None,
) -> str:
    cfg = cfg or load_student_learning_config()
    profiles = (cfg.get("students") or {}).get("profiles") or {}
    device_id = (profiles.get(student_id) or {}).get("memory_device_id")
    return resolve_assistant_display_name(memory_svc=memory_svc, device_id=device_id, cfg=cfg)


def build_onboarding_guidance(
    snap: ProfileSnapshot,
    *,
    grade_label: Optional[str] = None,
    assistant_name: str = DEFAULT_ASSISTANT_NAME,
) -> str:
    if not snap.needs_onboarding:
        return ""
    labels = [_MISSING_LABELS.get(m, m) for m in snap.missing]
    grade_hint = grade_label or snap.grade_label or "见 StudentContext"
    missing_line = "、".join(labels)
    assistant = (assistant_name or DEFAULT_ASSISTANT_NAME).strip() or DEFAULT_ASSISTANT_NAME
    return f"""## 用户画像预热（本轮优先）

孩子画像尚不完整，还缺：**{missing_line}**。
规则：
- 用**自然聊天**了解，不要像填表连问五题；一次最多问 **1～2** 个问题。
- 优先顺序：怎么称呼 → 确认年级（当前记录为 **{grade_hint}**）→ 一个爱好。
- 获知后务必调用 `agent_memory_write`：`category=user_profile` 记姓名/年级事实，`category=preference` 记爱好。
- 你自称 **{assistant}**。若孩子要给你起别名，调用 `agent_memory_write`：`category=preference`，`metadata` 含 `subject_key="{ASSISTANT_ALIAS_SUBJECT_KEY}"`，内容为「{assistant_alias_memory_content("别名")}」格式。
- 画像极空时**不要主动出题或推题**；若孩子坚持要练，最多 1 题，并穿插了解 Ta。
- 保持 {assistant} 口吻，友好简短。"""


def build_welcome_message(
    snap: ProfileSnapshot,
    *,
    assistant_name: str = DEFAULT_ASSISTANT_NAME,
) -> str:
    assistant = (assistant_name or DEFAULT_ASSISTANT_NAME).strip() or DEFAULT_ASSISTANT_NAME
    if snap.is_complete:
        name = snap.display_name or "同学"
        return (
            f"嗨 {name}！我是{assistant}～今天想学点什么，或者有不会的题想一起看看吗？😊"
        )
    if snap.has_display_name:
        name = snap.display_name
        if "interest" in snap.missing:
            return (
                f"嗨 {name}！我是{assistant}～你平时最喜欢做什么呀？"
                "聊完我们可以一起学习或做题哦～😊"
            )
        return f"嗨 {name}！我是{assistant}～今天想聊点什么，或者有不会的题？😊"
    return (
        f"嗨！我是{assistant}～初次见面，我怎么称呼你呀？"
        "你几年级？我们可以先认识一下，再一起学习～😊"
    )


def sync_preferred_name_to_onboarding(
    student_id: str,
    preferred_name: str,
    *,
    data_root: Optional[Path] = None,
    onboarding_svc: Optional[OnboardingService] = None,
) -> None:
    name = (preferred_name or "").strip()
    if not name:
        return
    cfg = load_student_learning_config()
    root = data_root or resolve_data_root(cfg)
    svc = onboarding_svc or OnboardingService(data_root=root)
    lay = layout_for(student_id, root)
    if lay.profile_path.is_file():
        try:
            raw = json.loads(lay.profile_path.read_text(encoding="utf-8"))
            if (raw.get("preferred_name") or "").strip() == name:
                return
        except Exception:
            pass
    try:
        svc.set_preferred_name(student_id, name)
        return
    except FileNotFoundError:
        pass
    except Exception:
        pass
    # Legacy fallback if StudentContext missing
    if not lay.profile_path.is_file():
        return
    try:
        raw = json.loads(lay.profile_path.read_text(encoding="utf-8"))
        if (raw.get("preferred_name") or "").strip() == name:
            return
        raw["preferred_name"] = name
        raw["updated_at"] = utc_now().isoformat().replace("+00:00", "Z")
        payload = json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=lay.profile_path.parent, suffix=".tmp", prefix=".profile-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, lay.profile_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        pass


def _read_onboarding_fields(student_id: str, root: Path) -> tuple[Optional[str], Optional[str]]:
    lay = layout_for(student_id, root)
    if not lay.profile_path.is_file():
        return None, None
    try:
        raw = json.loads(lay.profile_path.read_text(encoding="utf-8"))
        name = (raw.get("preferred_name") or "").strip() or None
        grade = (raw.get("grade") or "").strip() or None
        return name, grade
    except Exception:
        return None, None


def ingest_profile_clues_from_message(
    student_id: str,
    user_message: str,
    *,
    cfg: Optional[dict] = None,
    data_root: Optional[Path] = None,
    memory_svc=None,
    onboarding_svc: Optional[OnboardingService] = None,
) -> ProfileSnapshot:
    """Parse self-intro from chat and persist to M2 + onboarding (no tool call required)."""
    msg = (user_message or "").strip()
    cfg = cfg or load_student_learning_config()
    root = data_root or resolve_data_root(cfg)
    if not msg:
        return snapshot_for_student(student_id, cfg=cfg, data_root=root, memory_svc=memory_svc)

    onboard_name, onboard_grade = _read_onboarding_fields(student_id, root)
    name = _extract_name_from_text(msg) if not onboard_name else None
    grade = extract_grade_label_from_text(msg) if not onboard_grade else None
    interest = extract_interest_phrase_from_text(msg)
    if not any((name, grade, interest)):
        return snapshot_for_student(student_id, cfg=cfg, data_root=root, memory_svc=memory_svc)

    if memory_svc is None:
        from agent_platform.memory.service import MemoryService

        memory_svc = MemoryService()
    from agent_platform.memory.contracts import MemoryCategory, MemoryKind

    device_id = memory_device_for_student(student_id, cfg) or memory_svc.default_device_id
    svc = onboarding_svc or OnboardingService(data_root=root)

    if name:
        memory_svc.write(
            f"孩子姓名是{name}。",
            device_id=device_id,
            category=MemoryCategory.user_profile,
            kind=MemoryKind.fact,
        )
        svc.set_preferred_name(student_id, name)
    if grade:
        memory_svc.write(
            f"孩子上{grade}。",
            device_id=device_id,
            category=MemoryCategory.user_profile,
            kind=MemoryKind.fact,
        )
    if interest:
        memory_svc.write(
            f"爱好：{interest}",
            device_id=device_id,
            category=MemoryCategory.preference,
            kind=MemoryKind.preference,
        )

    refresh_student_display_name(
        student_id,
        cfg=cfg,
        data_root=root,
        memory_svc=memory_svc,
        onboarding_svc=svc,
    )
    return snapshot_for_student(student_id, cfg=cfg, data_root=root, memory_svc=memory_svc)


def refresh_student_display_name(
    student_id: str,
    *,
    cfg: Optional[dict] = None,
    data_root: Optional[Path] = None,
    memory_svc=None,
    onboarding_svc: Optional[OnboardingService] = None,
) -> Optional[str]:
    """Scan M2 for nickname and persist to onboarding profile when found."""
    cfg = cfg or load_student_learning_config()
    root = data_root or resolve_data_root(cfg)
    snap = snapshot_for_student(
        student_id,
        cfg=cfg,
        data_root=root,
        memory_svc=memory_svc,
    )
    if snap.display_name:
        sync_preferred_name_to_onboarding(
            student_id,
            snap.display_name,
            data_root=root,
            onboarding_svc=onboarding_svc,
        )
        return snap.display_name
    return None


def ensure_onboarding_stage_if_needed(
    student_id: str,
    snap: ProfileSnapshot,
    *,
    cfg: Optional[dict] = None,
    data_root: Optional[Path] = None,
) -> None:
    if not snap.needs_onboarding:
        return
    cfg = cfg or load_student_learning_config()
    root = data_root or resolve_data_root(cfg)
    ctx_svc = StudentContextService(cfg, data_root=root)
    if not ctx_svc.exists(student_id):
        return
    ctx = ctx_svc.get(student_id)
    if ctx.pipeline_stage != PipelineStage.onboarding:
        ctx_svc.patch(student_id, StudentContextPatch(pipeline_stage=PipelineStage.onboarding))


def maybe_advance_from_onboarding(
    student_id: str,
    *,
    cfg: Optional[dict] = None,
    data_root: Optional[Path] = None,
    memory_svc=None,
) -> bool:
    """If profile complete and stage is onboarding, promote to learning."""
    cfg = cfg or load_student_learning_config()
    root = data_root or resolve_data_root(cfg)
    refresh_student_display_name(
        student_id,
        cfg=cfg,
        data_root=root,
        memory_svc=memory_svc,
    )
    snap = snapshot_for_student(student_id, cfg=cfg, data_root=root, memory_svc=memory_svc)
    if snap.display_name:
        sync_preferred_name_to_onboarding(student_id, snap.display_name, data_root=root)
    if not snap.is_complete:
        ensure_onboarding_stage_if_needed(student_id, snap, cfg=cfg, data_root=root)
        return False
    ctx_svc = StudentContextService(cfg, data_root=root)
    if not ctx_svc.exists(student_id):
        return False
    ctx = ctx_svc.get(student_id)
    if ctx.pipeline_stage == PipelineStage.onboarding:
        ctx_svc.patch(student_id, StudentContextPatch(pipeline_stage=PipelineStage.learning))
        return True
    return False

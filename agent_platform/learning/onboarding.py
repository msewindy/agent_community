"""Student onboarding profile (P0)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    StudentContextInit,
    StudentOnboardingProfile,
    StudentSelfAssessment,
    utc_now,
)
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.store import layout_for
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.subject_pilot import pilot_unit_id


class OnboardingService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        context_svc: Optional[StudentContextService] = None,
        catalog: Optional[KpCatalogService] = None,
    ) -> None:
        self._cfg = load_student_learning_config()
        self._data_root = data_root
        self._ctx = context_svc or StudentContextService(data_root=data_root)
        self._catalog = catalog or KpCatalogService()

    def _save_profile(self, path: Path, profile: StudentOnboardingProfile) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=".profile-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def load_profile(self, student_id: str) -> StudentOnboardingProfile:
        lay = layout_for(student_id, self._data_root)
        if not lay.profile_path.is_file():
            raise FileNotFoundError(f"onboarding profile not found: {student_id}")
        raw = json.loads(lay.profile_path.read_text(encoding="utf-8"))
        return StudentOnboardingProfile.model_validate(raw)

    def onboard(
        self,
        student_id: str,
        *,
        grade: str = "二年级",
        grade_level: int = 2,
        primary_subject: str = "数学",
        active_unit_id: Optional[str] = None,
        self_assessment: Optional[StudentSelfAssessment] = None,
    ) -> StudentOnboardingProfile:
        pilot = self._cfg.get("pilot") or {}
        units = pilot.get("units") or {}
        if active_unit_id is None:
            active_unit_id = pilot_unit_id(units, primary_subject)
        if not active_unit_id:
            active_unit_id = (self._cfg.get("default_curriculum") or {}).get("unit_id")
        self._catalog.assert_student_may_access_unit(grade_level, str(active_unit_id))
        unit = self._catalog.get_unit(str(active_unit_id))

        defaults = dict(self._cfg.get("default_curriculum") or {})
        defaults.update(
            {
                "grade": grade,
                "grade_level": grade_level,
                "subject": unit.subject,
                "unit_id": unit.unit_id,
                "unit_title": unit.unit_title,
            }
        )
        from agent_platform.learning.contracts import Curriculum, PipelineStage

        if not self._ctx.exists(student_id):
            self._ctx.init(
                student_id,
                StudentContextInit(
                    curriculum=Curriculum.model_validate(defaults),
                    pipeline_stage=PipelineStage.onboarding,
                ),
            )

        profile = StudentOnboardingProfile(
            student_id=student_id,
            updated_at=utc_now(),
            grade=grade,
            grade_level=grade_level,
            primary_subject=primary_subject,
            active_unit_id=unit.unit_id,
            self_assessment=self_assessment or StudentSelfAssessment(),
        )
        lay = layout_for(student_id, self._data_root)
        self._save_profile(lay.profile_path, profile)
        return profile

    def sync_active_unit(self, student_id: str, unit_id: str, *, subject: Optional[str] = None) -> None:
        """Keep onboarding profile aligned after parent-panel unit switch."""
        try:
            profile = self.load_profile(student_id)
        except FileNotFoundError:
            return
        profile.active_unit_id = unit_id
        profile.updated_at = utc_now()
        if subject:
            profile.primary_subject = subject
        lay = layout_for(student_id, self._data_root)
        self._save_profile(lay.profile_path, profile)

    def set_preferred_name(self, student_id: str, preferred_name: str) -> StudentOnboardingProfile:
        """Persist nickname on L1 onboarding profile (create minimal profile if missing)."""
        name = (preferred_name or "").strip()
        if not name:
            raise ValueError("preferred_name must not be empty")
        lay = layout_for(student_id, self._data_root)
        try:
            profile = self.load_profile(student_id)
        except FileNotFoundError:
            ctx = self._ctx.get(student_id)
            profile = StudentOnboardingProfile(
                student_id=student_id,
                updated_at=utc_now(),
                grade=ctx.curriculum.grade,
                grade_level=int(ctx.curriculum.grade_level or 3),
                primary_subject=ctx.curriculum.subject,
                active_unit_id=ctx.curriculum.unit_id,
                preferred_name=name,
            )
        else:
            profile.preferred_name = name
            profile.updated_at = utc_now()
        self._save_profile(lay.profile_path, profile)
        return profile

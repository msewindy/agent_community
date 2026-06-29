"""JSONL experience store + Markdown skill files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agent_platform.evolution._config import load_evolution_config, repo_root
from agent_platform.evolution.contracts import CurriculumLogEntry, ExperienceRecord, SkillRecord


class EvolutionStore:
    def __init__(self, root: Path | None = None) -> None:
        cfg = load_evolution_config()
        store_cfg = cfg.get("store") or {}
        base = root or (repo_root() / str(store_cfg.get("root", "skills_data")))
        self.root = Path(base)
        self.experiences_path = self.root / str(store_cfg.get("experiences_file", "experiences.jsonl"))
        self.curriculum_log_path = self.root / str(
            store_cfg.get("curriculum_log_file", "curriculum_log.jsonl")
        )
        self.skills_dir = self.root / str(store_cfg.get("skills_dir", "skills"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def append_experience(self, exp: ExperienceRecord) -> None:
        line = exp.model_dump_json() + "\n"
        with self.experiences_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def append_curriculum_log(self, entry: CurriculumLogEntry) -> None:
        line = entry.model_dump_json() + "\n"
        with self.curriculum_log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def list_curriculum_log(self, limit: int = 500) -> list[CurriculumLogEntry]:
        if not self.curriculum_log_path.is_file():
            return []
        rows: list[CurriculumLogEntry] = []
        for line in self.curriculum_log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(CurriculumLogEntry.model_validate_json(line))
        return rows[-limit:]

    def list_experiences(self, limit: int = 500) -> list[ExperienceRecord]:
        if not self.experiences_path.is_file():
            return []
        rows: list[ExperienceRecord] = []
        for line in self.experiences_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(ExperienceRecord.model_validate_json(line))
        return rows[-limit:]

    def save_skill(self, skill: SkillRecord) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill.skill_id[:12])
        name_part = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in skill.name[:60]
        )
        path = self.skills_dir / f"{safe}_{name_part}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = skill.model_dump_json(indent=2)
        md = (
            f"# Skill: {skill.name}\n\n"
            f"**topic**: {skill.topic}  \n"
            f"**confidence**: {skill.confidence:.2f}  \n"
            f"**status**: {skill.status.value}  \n\n"
            f"## Triggers\n"
            + "\n".join(f"- {t}" for t in skill.triggers)
            + f"\n\n## Procedure\n\n{skill.procedure}\n\n"
            f"## Guardrails\n\n{skill.guardrails}\n\n"
            f"## Machine JSON\n\n```json\n{body}\n```\n"
        )
        path.write_text(md, encoding="utf-8")
        return path

    def list_skills(self) -> list[SkillRecord]:
        out: list[SkillRecord] = []
        for p in sorted(self.skills_dir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            marker = "```json\n"
            if marker not in text:
                continue
            chunk = text.split(marker, 1)[1].split("```", 1)[0]
            out.append(SkillRecord.model_validate_json(chunk))
        return out

    def clear_all(self) -> None:
        if self.experiences_path.is_file():
            self.experiences_path.unlink()
        if self.curriculum_log_path.is_file():
            self.curriculum_log_path.unlink()
        for p in self.skills_dir.glob("*.md"):
            p.unlink()

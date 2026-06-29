#!/usr/bin/env python3
"""Phase 7 acceptance — evolution bridge, KPI, seed verify."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.evolution_bridge import LearningEvolutionBridge
from agent_platform.learning.kpi_report import LearningKpiService
from agent_platform.learning.seed_manifest import verify_seed_package
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase7() -> int:
    seed = verify_seed_package()
    if not seed.ok:
        return _fail(f"seed verify: {seed.errors}")

    with tempfile.TemporaryDirectory(prefix="learning-p7-") as td:
        root = Path(td) / "student_data"
        ctx_svc = StudentContextService(data_root=root)
        bridge = LearningEvolutionBridge(data_root=root)
        att_svc = AttemptService(data_root=root, context_svc=ctx_svc, evolution_bridge=bridge)
        kpi_svc = LearningKpiService(data_root=root)
        sid = "demo-stu-p7"

        ctx_svc.init_from_defaults(sid)

        for _ in range(3):
            att_svc.submit(sid, "q-g2m-002", "80")
        att_svc.submit(sid, "q-g2m-002", "85")
        att_svc.submit(sid, "q-g2m-003", "83")
        r = att_svc.submit(sid, "q-g2m-009", "75")

        if not any(p.promoted for p in r.skill_promotions):
            return _fail("expected skill promotion on mastered gap")

        skills = bridge.list_personal_skills(sid)
        if not skills:
            return _fail("no personal skills in evolution dir")

        report = kpi_svc.build_report(sid, period_days=90)
        if report.attempts_total < 6:
            return _fail(f"attempts_total={report.attempts_total}")

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}

        kr = subprocess.run(
            [sys.executable, str(cli), "--data-root", str(root), "kpi", "report", sid, "--days", "90"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if kr.returncode != 0:
            return _fail(f"cli kpi report: {kr.stderr}")
        payload = json.loads(kr.stdout)
        if payload.get("attempts_total", 0) < 6:
            return _fail(f"cli kpi payload: {payload}")

        sv = subprocess.run(
            [sys.executable, str(cli), "seed", "verify"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if sv.returncode != 0:
            return _fail(f"cli seed verify: {sv.stderr}")

        _ok("seed package verify")
        _ok("gap mastered promotes personal skill")
        _ok("KPI report JSON")
        _ok("cli kpi report + seed verify")

    print("accept_learning_phase7: PASS")
    return 0


def main() -> int:
    return accept_phase7()


if __name__ == "__main__":
    raise SystemExit(main())

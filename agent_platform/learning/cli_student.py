#!/usr/bin/env python3
"""Student Jarvis CLI — context init / show / set-stage (Phase 1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.parent_report import ParentReportService
from agent_platform.learning.contracts import Curriculum, LearningGoal, PipelineStage, StudentContextInit
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.evolution_bridge import LearningEvolutionBridge
from agent_platform.learning.kpi_report import LearningKpiService
from agent_platform.learning.learning_proactive import LearningProactiveService
from agent_platform.learning.push_engine import PushEngineService
from agent_platform.learning.seed_manifest import verify_seed_package
from agent_platform.learning.study_plan import StudyPlanService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_ingest_review import KpIngestReviewService, ResolutionAction
from agent_platform.learning.textbook_ingest import TextbookIngestService


def _svc(args: argparse.Namespace) -> StudentContextService:
    root = getattr(args, "data_root", None)
    return StudentContextService(data_root=Path(root) if root else None)


def _attempt_svc(args: argparse.Namespace) -> AttemptService:
    root = getattr(args, "data_root", None)
    data_root = Path(root) if root else None
    return AttemptService(data_root=data_root)


def _gap_svc(args: argparse.Namespace) -> GapMapService:
    root = getattr(args, "data_root", None)
    return GapMapService(data_root=Path(root) if root else None)


def _push_svc(args: argparse.Namespace) -> PushEngineService:
    root = getattr(args, "data_root", None)
    data_root = Path(root) if root else None
    return PushEngineService(data_root=data_root)


def _plan_svc(args: argparse.Namespace) -> StudyPlanService:
    root = getattr(args, "data_root", None)
    return StudyPlanService(data_root=Path(root) if root else None)


def _proactive_svc(args: argparse.Namespace) -> LearningProactiveService:
    root = getattr(args, "data_root", None)
    return LearningProactiveService(data_root=Path(root) if root else None)


def _kpi_svc(args: argparse.Namespace) -> LearningKpiService:
    root = getattr(args, "data_root", None)
    return LearningKpiService(data_root=Path(root) if root else None)


def _bank() -> QuestionBankService:
    return QuestionBankService()


def cmd_init(args: argparse.Namespace) -> int:
    svc = _svc(args)
    if args.from_defaults:
        try:
            ctx = svc.init_from_defaults(args.student_id, unit_id=args.unit)
        except FileExistsError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    else:
        cur = Curriculum(
            grade=args.grade,
            subject=args.subject,
            unit_id=args.unit,
            unit_title=args.title,
            textbook_ref=args.textbook_ref,
        )
        goal = None
        if args.goal_label:
            goal = LearningGoal(label=args.goal_label)
        try:
            ctx = svc.init(
                args.student_id,
                StudentContextInit(
                    curriculum=cur,
                    pipeline_stage=PipelineStage(args.stage),
                    goal=goal,
                ),
            )
        except FileExistsError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    print(json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    svc = _svc(args)
    try:
        ctx = svc.get(args.student_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_set_stage(args: argparse.Namespace) -> int:
    svc = _svc(args)
    from agent_platform.learning.contracts import StudentContextPatch

    try:
        ctx = svc.patch(
            args.student_id,
            StudentContextPatch(pipeline_stage=PipelineStage(args.stage)),
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    svc = _svc(args)
    try:
        block = svc.to_prompt_block(student_id=args.student_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(block)
    return 0


def cmd_question_list(args: argparse.Namespace) -> int:
    bank = _bank()
    items = bank.list_questions(unit_id=args.unit)
    payload = [q.model_dump(mode="json") for q in items]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_question_show(args: argparse.Namespace) -> int:
    bank = _bank()
    try:
        q = bank.get(args.question_id)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(q.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_attempt_submit(args: argparse.Namespace) -> int:
    svc = _attempt_svc(args)
    try:
        result = svc.submit(args.student_id, args.question_id, args.answer)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_attempt_list(args: argparse.Namespace) -> int:
    svc = _attempt_svc(args)
    items = svc.list(args.student_id, limit=args.limit)
    payload = [a.model_dump(mode="json") for a in items]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_gap_list(args: argparse.Namespace) -> int:
    svc = _gap_svc(args)
    try:
        items = svc.query(args.student_id, limit=args.limit)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    payload = [g.model_dump(mode="json") for g in items]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_gap_show(args: argparse.Namespace) -> int:
    svc = _gap_svc(args)
    try:
        gap = svc.get_gap(args.student_id, args.gap_id)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(gap.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_push_peek(args: argparse.Namespace) -> int:
    svc = _push_svc(args)
    try:
        items = svc.peek(args.student_id, limit=args.limit)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    payload = [i.model_dump(mode="json") for i in items]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_push_fetch(args: argparse.Namespace) -> int:
    svc = _push_svc(args)
    try:
        result = svc.fetch(args.student_id, count=args.count)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_push_rebuild(args: argparse.Namespace) -> int:
    svc = _push_svc(args)
    try:
        queue = svc.rebuild(args.student_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(queue.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_bank_import(args: argparse.Namespace) -> int:
    bank = _bank()
    count = bank.import_seed_to_sqlite()
    print(json.dumps({"imported": count, "sqlite_path": str(bank.sqlite_path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_plan_generate(args: argparse.Namespace) -> int:
    svc = _plan_svc(args)
    try:
        plan = svc.generate(args.student_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_proactive_list(args: argparse.Namespace) -> int:
    svc = _proactive_svc(args)
    items = svc.list_messages(args.student_id, limit=args.limit)
    payload = [m.model_dump(mode="json") for m in items]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_kpi_report(args: argparse.Namespace) -> int:
    svc = _kpi_svc(args)
    try:
        report = svc.build_report(args.student_id, period_days=args.days)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    root = getattr(args, "data_root", None)
    data_root = Path(root) if root else None
    svc = OnboardingService(data_root=data_root)
    try:
        profile = svc.onboard(
            args.student_id,
            grade=args.grade,
            grade_level=args.grade_level,
            primary_subject=args.subject,
            active_unit_id=args.unit or None,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_parent_report(args: argparse.Namespace) -> int:
    root = getattr(args, "data_root", None)
    data_root = Path(root) if root else None
    svc = ParentReportService(data_root=data_root)
    try:
        report = svc.build_weekly_report(args.student_id, period_days=args.days)
        if args.save:
            path = svc.save_report(report)
            payload = report.model_dump(mode="json")
            payload["_saved_path"] = str(path)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


def _ingest_svc(args: argparse.Namespace) -> TextbookIngestService:
    root = getattr(args, "data_root", None)
    return TextbookIngestService(data_root=Path(root) if root else None)


def _review_svc(args: argparse.Namespace) -> KpIngestReviewService:
    return KpIngestReviewService(ingest_svc=_ingest_svc(args))


def cmd_catalog_tree(args: argparse.Namespace) -> int:
    svc = KpCatalogService()
    tree = svc.list_tree()
    payload = tree.model_dump(mode="json")
    if args.subject or args.grade is not None:
        subjects = payload.get("subjects") or []
        if args.subject:
            subjects = [s for s in subjects if s.get("subject") == args.subject]
        if args.grade is not None:
            for subj in subjects:
                subj["grades"] = [g for g in subj.get("grades") or [] if g.get("grade") == args.grade]
        payload = {"subjects": subjects}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_submit(args: argparse.Namespace) -> int:
    svc = _ingest_svc(args)
    path = Path(args.path)
    source_type = args.type.lower()
    kwargs = {
        "grade_level": args.grade_level,
        "subject": args.subject or None,
    }
    try:
        if source_type == "pdf":
            job = svc.submit_pdf(path, **kwargs)
        elif source_type == "photo":
            job = svc.submit_photo(path, **kwargs)
        elif source_type == "document":
            job = svc.submit_document(path, **kwargs)
        elif source_type in ("kp-doc", "kp_doc"):
            job = svc.submit_kp_document(path)
        else:
            print(f"ERROR: unknown ingest type: {args.type}", file=sys.stderr)
            return 1
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_list(args: argparse.Namespace) -> int:
    svc = _ingest_svc(args)
    jobs = svc.list_jobs()
    payload = [j.model_dump(mode="json") for j in jobs]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_show(args: argparse.Namespace) -> int:
    svc = _ingest_svc(args)
    try:
        job = svc.get_job(args.job_id)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_diff(args: argparse.Namespace) -> int:
    review = _review_svc(args)
    try:
        job = review._ingest.get_job(args.job_id)
        snapshot = review.build_snapshot(job)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(snapshot.catalog_diff.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_review(args: argparse.Namespace) -> int:
    review = _review_svc(args)
    try:
        job = review.refresh_job_review(args.job_id)
        snapshot = review.build_snapshot(job)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    payload = {
        "job_id": job.job_id,
        "status": job.status.value,
        "ready_to_approve": snapshot.ready_to_approve,
        "blocking_unresolved": snapshot.blocking_unresolved,
        "checklist": [c.model_dump(mode="json") for c in snapshot.checklist],
        "conflicts": [c.model_dump(mode="json") for c in snapshot.catalog_diff.conflicts],
        "conflict_resolutions": [r.model_dump(mode="json") for r in snapshot.conflict_resolutions],
        "summary": snapshot.catalog_diff.summary.model_dump(mode="json"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_resolve(args: argparse.Namespace) -> int:
    review = _review_svc(args)
    try:
        action = ResolutionAction(args.action)
        job = review.set_resolution(
            args.job_id,
            args.conflict_id,
            action,
            new_knowledge_point_id=args.new_kp_id,
            note=args.note,
        )
    except (KeyError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_review_confirm(args: argparse.Namespace) -> int:
    review = _review_svc(args)
    try:
        job = review.set_review_flag(args.job_id, args.flag, value=not args.unset)
    except (KeyError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    snapshot = review.build_snapshot(job)
    print(
        json.dumps(
            {
                "job_id": job.job_id,
                "flag": args.flag,
                "value": job.review_flags.get(args.flag),
                "ready_to_approve": snapshot.ready_to_approve,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_ingest_approve(args: argparse.Namespace) -> int:
    review = _review_svc(args)
    try:
        result = review.approve(args.job_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_reject(args: argparse.Namespace) -> int:
    review = _review_svc(args)
    try:
        job = review.reject(args.job_id, reason=args.reason)
    except (KeyError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_seed_verify(args: argparse.Namespace) -> int:
    result = verify_seed_package()
    payload = {
        "ok": result.ok,
        "question_count": result.question_count,
        "taxonomy_count": result.taxonomy_count,
        "remediation_skill_count": result.remediation_skill_count,
        "warnings": result.warnings,
        "errors": result.errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _default_curriculum() -> dict:
    return load_student_learning_config().get("default_curriculum") or {}


def main() -> int:
    defaults = _default_curriculum()
    p = argparse.ArgumentParser(description="Student Jarvis — learning context CLI")
    p.add_argument("--data-root", type=Path, default=None, help="Override student_data root")
    sub = p.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init", help="Initialize student context")
    init_p.add_argument("student_id")
    init_p.add_argument("--from-defaults", action="store_true", help="Use student_learning.yaml defaults")
    init_p.add_argument("--unit", default=str(defaults.get("unit_id", "math-g2-add-sub-100")))
    init_p.add_argument("--grade", default=str(defaults.get("grade", "二年级")))
    init_p.add_argument("--subject", default=str(defaults.get("subject", "数学")))
    init_p.add_argument("--title", default=str(defaults.get("unit_title", "100以内加减法")))
    init_p.add_argument("--textbook-ref", default=None)
    init_p.add_argument("--stage", default="onboarding", choices=[s.value for s in PipelineStage])
    init_p.add_argument("--goal-label", default=None)
    init_p.set_defaults(func=cmd_init)

    show_p = sub.add_parser("show", help="Show context JSON")
    show_p.add_argument("student_id")
    show_p.set_defaults(func=cmd_show)

    st_p = sub.add_parser("set-stage", help="Update pipeline_stage")
    st_p.add_argument("student_id")
    st_p.add_argument("stage", choices=[s.value for s in PipelineStage])
    st_p.set_defaults(func=cmd_set_stage)

    pr_p = sub.add_parser("prompt", help="Print pre_llm prompt block")
    pr_p.add_argument("student_id")
    pr_p.set_defaults(func=cmd_prompt)

    q_list = sub.add_parser("question", help="Question bank commands")
    q_sub = q_list.add_subparsers(dest="question_cmd", required=True)
    ql = q_sub.add_parser("list", help="List seed questions")
    ql.add_argument("--unit", default=None)
    ql.set_defaults(func=cmd_question_list)
    qs = q_sub.add_parser("show", help="Show one question")
    qs.add_argument("question_id")
    qs.set_defaults(func=cmd_question_show)

    att = sub.add_parser("attempt", help="Attempt commands")
    att_sub = att.add_subparsers(dest="attempt_cmd", required=True)
    ats = att_sub.add_parser("submit", help="Submit an answer")
    ats.add_argument("student_id")
    ats.add_argument("question_id")
    ats.add_argument("answer")
    ats.set_defaults(func=cmd_attempt_submit)
    atl = att_sub.add_parser("list", help="List attempts")
    atl.add_argument("student_id")
    atl.add_argument("--limit", type=int, default=50)
    atl.set_defaults(func=cmd_attempt_list)

    gap = sub.add_parser("gap", help="Gap map commands")
    gap_sub = gap.add_subparsers(dest="gap_cmd", required=True)
    gl = gap_sub.add_parser("list", help="List gaps by priority")
    gl.add_argument("student_id")
    gl.add_argument("--limit", type=int, default=10)
    gl.set_defaults(func=cmd_gap_list)
    gs = gap_sub.add_parser("show", help="Show one gap")
    gs.add_argument("student_id")
    gs.add_argument("gap_id")
    gs.set_defaults(func=cmd_gap_show)

    push = sub.add_parser("push", help="Push queue commands")
    push_sub = push.add_subparsers(dest="push_cmd", required=True)
    pp = push_sub.add_parser("peek", help="Peek queue head")
    pp.add_argument("student_id")
    pp.add_argument("--limit", type=int, default=5)
    pp.set_defaults(func=cmd_push_peek)
    pf = push_sub.add_parser("fetch", help="Fetch next question batch")
    pf.add_argument("student_id")
    pf.add_argument("--count", type=int, default=None)
    pf.set_defaults(func=cmd_push_fetch)
    pr = push_sub.add_parser("rebuild", help="Rebuild push queue")
    pr.add_argument("student_id")
    pr.set_defaults(func=cmd_push_rebuild)

    bank = sub.add_parser("bank", help="Question bank maintenance")
    bank_sub = bank.add_subparsers(dest="bank_cmd", required=True)
    bi = bank_sub.add_parser("import", help="Import seed JSON into SQLite")
    bi.set_defaults(func=cmd_bank_import)

    plan = sub.add_parser("plan", help="Study plan commands")
    plan_sub = plan.add_subparsers(dest="plan_cmd", required=True)
    pg = plan_sub.add_parser("generate", help="Generate micro study plan")
    pg.add_argument("student_id")
    pg.set_defaults(func=cmd_plan_generate)

    pro = sub.add_parser("proactive", help="Learning proactive messages")
    pro_sub = pro.add_subparsers(dest="proactive_cmd", required=True)
    pl = pro_sub.add_parser("list", help="List proactive messages")
    pl.add_argument("student_id")
    pl.add_argument("--limit", type=int, default=20)
    pl.set_defaults(func=cmd_proactive_list)

    kpi = sub.add_parser("kpi", help="Pilot KPI reports")
    kpi_sub = kpi.add_subparsers(dest="kpi_cmd", required=True)
    kr = kpi_sub.add_parser("report", help="Generate KPI report")
    kr.add_argument("student_id")
    kr.add_argument("--days", type=int, default=90)
    kr.set_defaults(func=cmd_kpi_report)

    seed = sub.add_parser("seed", help="Seed package verification")
    seed_sub = seed.add_subparsers(dest="seed_cmd", required=True)
    sv = seed_sub.add_parser("verify", help="Verify taxonomy/question/skills seed")
    sv.set_defaults(func=cmd_seed_verify)

    ob = sub.add_parser("onboard", help="P0 onboarding (grade + unit + profile)")
    ob.add_argument("student_id")
    ob.add_argument("--grade", default=str(defaults.get("grade", "二年级")))
    ob.add_argument("--grade-level", type=int, default=int(defaults.get("grade_level", 2)))
    ob.add_argument("--subject", default=str(defaults.get("subject", "数学")))
    ob.add_argument("--unit", default=None, help="Override active unit_id")
    ob.set_defaults(func=cmd_onboard)

    pr = sub.add_parser("parent-report", help="Generate parent weekly report")
    pr.add_argument("student_id")
    pr.add_argument("--days", type=int, default=7)
    pr.add_argument("--save", action="store_true", help="Persist report JSON under student dir")
    pr.set_defaults(func=cmd_parent_report)

    ingest = sub.add_parser("ingest", help="Textbook / KP document ingest")
    ingest_sub = ingest.add_subparsers(dest="ingest_cmd", required=True)
    isub = ingest_sub.add_parser("submit", help="Submit PDF/photo/document or .kp.md for review")
    isub.add_argument(
        "--type",
        required=True,
        choices=["pdf", "photo", "document", "kp-doc"],
    )
    isub.add_argument("--path", required=True, type=Path)
    isub.add_argument("--subject", default=None, help="数学 / 语文 / 英语 (kp-doc 从文档 frontmatter 读取)")
    isub.add_argument("--grade-level", type=int, default=int(defaults.get("grade_level", 2)))
    isub.set_defaults(func=cmd_ingest_submit)
    ilist = ingest_sub.add_parser("list", help="List ingest jobs")
    ilist.set_defaults(func=cmd_ingest_list)
    ishow = ingest_sub.add_parser("show", help="Show one ingest job")
    ishow.add_argument("job_id")
    ishow.set_defaults(func=cmd_ingest_show)
    idiff = ingest_sub.add_parser("diff", help="Show catalog diff for kp-doc job")
    idiff.add_argument("job_id")
    idiff.set_defaults(func=cmd_ingest_diff)
    irev = ingest_sub.add_parser("review", help="Review checklist + conflicts for job")
    irev.add_argument("job_id")
    irev.set_defaults(func=cmd_ingest_review)
    ires = ingest_sub.add_parser("resolve", help="Resolve one catalog conflict")
    ires.add_argument("job_id")
    ires.add_argument("conflict_id")
    ires.add_argument(
        "action",
        choices=[a.value for a in ResolutionAction],
    )
    ires.add_argument("--new-kp-id", default=None)
    ires.add_argument("--note", default=None)
    ires.set_defaults(func=cmd_ingest_resolve)
    icon = ingest_sub.add_parser("review-confirm", help="Set R1/R6 review confirmation flags")
    icon.add_argument("job_id")
    icon.add_argument(
        "--flag",
        required=True,
        choices=["confirm_subject_grade", "confirm_write"],
    )
    icon.add_argument("--unset", action="store_true")
    icon.set_defaults(func=cmd_ingest_review_confirm)
    iap = ingest_sub.add_parser("approve", help="Merge approved kp-doc job into kp_catalog.json")
    iap.add_argument("job_id")
    iap.set_defaults(func=cmd_ingest_approve)
    irj = ingest_sub.add_parser("reject", help="Reject ingest job without writing catalog")
    irj.add_argument("job_id")
    irj.add_argument("--reason", default=None)
    irj.set_defaults(func=cmd_ingest_reject)

    cat = sub.add_parser("catalog", help="KP catalog commands")
    cat_sub = cat.add_subparsers(dest="catalog_cmd", required=True)
    ct = cat_sub.add_parser("tree", help="Hierarchical catalog tree (subject/grade/unit/kp)")
    ct.add_argument("--subject", default=None)
    ct.add_argument("--grade", type=int, default=None)
    ct.set_defaults(func=cmd_catalog_tree)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

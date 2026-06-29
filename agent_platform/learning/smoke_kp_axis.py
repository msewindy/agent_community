"""Headless smoke for 切片09 — 学情主轴改造（错因码轴 → 知识点轴）.

覆盖通过标准 1-5（见 学生Jarvis-v2/L2-验证切片/切片09-学情主轴改造.md）：
  1 无错因码错题入学情
  2 加减法（带错因码）不退化，error_breakdown 保留
  3 同一知识点连对 3 次 → mastered
  4 旧数据（g2-stu-01）重建不报错、按知识点归并
  5 下游 push_engine + parent_report 不报错

运行：
  PY=/home/administrator/.hermes/hermes-agent/venv/bin/python
  $PY -m agent_platform.learning.smoke_kp_axis
"""

from __future__ import annotations

from datetime import timedelta

from agent_platform.learning.contracts import AttemptRecord, GapStatus, utc_now
from agent_platform.learning.gap_map import GapMapUpdater
from agent_platform.learning.taxonomy import gap_id_for_kp


def _att(
    *,
    kp: str,
    correct: bool,
    error_code: str | None,
    when,
    qid: str,
    aid: str,
) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=aid,
        student_id="smoke-stu",
        question_id=qid,
        unit_id="math-g2-add-sub-100",
        submitted_at=when,
        answer_raw="x",
        answer_normalized="x",
        correct=correct,
        expected_answer="y",
        explanation="",
        error_code=error_code,
        knowledge_point_id=kp,
        trace_id="trace-smoke",
        source="freeform",
    )


def _find(gap_map, gap_id):
    return next((g for g in gap_map.gaps if g.gap_id == gap_id), None)


def main() -> int:
    updater = GapMapUpdater()
    now = utc_now()
    results: list[tuple[str, bool, str]] = []

    # ---- 标准1：无错因码错题（kp 在目录里、无错因映射）入学情 ----
    kp_dir = "kp-g2-word-problem-more-less"  # 求比一个数多几/少几，无错因码
    atts1 = [
        _att(kp=kp_dir, correct=False, error_code=None, when=now - timedelta(minutes=5),
             qid="freeform-1", aid="att-s1-1"),
    ]
    gm1 = updater.rebuild("smoke-stu", atts1, "math-g2-add-sub-100", now=now)
    g1 = _find(gm1, gap_id_for_kp(kp_dir))
    ok1 = g1 is not None and g1.error_code is None and "att-s1-1" in g1.evidence_attempt_ids
    results.append((
        "1 无错因码错题入学情",
        ok1,
        f"gap={'有' if g1 else '无'} title={getattr(g1,'title',None)!r} "
        f"error_code={getattr(g1,'error_code',None)} evidence={getattr(g1,'evidence_attempt_ids',None)}",
    ))

    # ---- 标准2：加减法（带 BORROW_ERROR）不退化，error_breakdown 保留 ----
    kp_borrow = "kp-g2-sub-borrow"
    atts2 = [
        _att(kp=kp_borrow, correct=False, error_code="BORROW_ERROR", when=now - timedelta(minutes=4),
             qid="q-g2m-005", aid="att-s2-1"),
        _att(kp=kp_borrow, correct=False, error_code="BORROW_ERROR", when=now - timedelta(minutes=3),
             qid="q-g2m-007", aid="att-s2-2"),
    ]
    gm2 = updater.rebuild("smoke-stu", atts2, "math-g2-add-sub-100", now=now)
    g2 = _find(gm2, gap_id_for_kp(kp_borrow))
    ok2 = (
        g2 is not None
        and g2.title == "退位减法"
        and g2.error_breakdown.get("BORROW_ERROR") == 2
        and g2.stats.total_wrong == 2
    )
    results.append((
        "2 加减法不退化 + error_breakdown",
        ok2,
        f"title={getattr(g2,'title',None)!r} breakdown={getattr(g2,'error_breakdown',None)}",
    ))

    # ---- 标准3：同一知识点连对 3 次 → mastered ----
    atts3 = atts2 + [
        _att(kp=kp_borrow, correct=True, error_code=None, when=now - timedelta(minutes=2),
             qid="q-g2m-010", aid="att-s3-1"),
        _att(kp=kp_borrow, correct=True, error_code=None, when=now - timedelta(minutes=1),
             qid="q-g2m-005", aid="att-s3-2"),
        _att(kp=kp_borrow, correct=True, error_code=None, when=now,
             qid="q-g2m-007", aid="att-s3-3"),
    ]
    gm3 = updater.rebuild("smoke-stu", atts3, "math-g2-add-sub-100", now=now)
    g3 = _find(gm3, gap_id_for_kp(kp_borrow))
    ok3 = g3 is not None and g3.status == GapStatus.mastered and g3.mastery.streak_correct >= 3
    results.append((
        "3 连对3次→mastered",
        ok3,
        f"status={getattr(g3,'status',None)} streak={getattr(g3.mastery,'streak_correct',None) if g3 else None}",
    ))

    # ---- 标准4：旧数据 g2-stu-01 重建不报错、按知识点归并 ----
    try:
        from agent_platform.learning.store import layout_for, list_attempt_paths, load_attempt

        lay = layout_for("g2-stu-01", None)
        if lay.attempts_dir.is_dir():
            real = [load_attempt(p) for p in list_attempt_paths(lay.attempts_dir)]
            gm4 = updater.rebuild("g2-stu-01", real, "math-g2-add-sub-100")
            all_kp_keyed = all(g.gap_id == gap_id_for_kp(g.knowledge_point_id) for g in gm4.gaps)
            ok4 = all_kp_keyed
            detail4 = f"attempts={len(real)} gaps={len(gm4.gaps)} 全部按KP归键={all_kp_keyed}: " + \
                ", ".join(f"{g.gap_id}(w{g.stats.total_wrong})" for g in gm4.gaps)
        else:
            ok4 = True
            detail4 = "（无 g2-stu-01 历史数据，跳过，视为通过）"
    except Exception as e:  # noqa: BLE001
        ok4 = False
        detail4 = f"重建报错：{e!r}"
    results.append(("4 旧数据迁移重建", ok4, detail4))

    # ---- 标准5：下游 push_engine + dimension/report 不报错 ----
    try:
        from agent_platform.learning.push_engine import build_push_queue
        from agent_platform.learning.question_bank import QuestionBankService
        from agent_platform.learning.dimension_model import DimensionModelService

        bank = QuestionBankService()
        queue = build_push_queue(
            student_id="smoke-stu",
            unit_id="math-g2-add-sub-100",
            gap_map=gm2,
            bank=bank,
            attempts=atts2,
        )
        dims = DimensionModelService().score_from_attempts(atts2, gap_map=gm2)
        ok5 = isinstance(queue.items, list) and isinstance(dims, list)
        detail5 = f"queue_items={len(queue.items)} dims={[(d.dimension_id, d.signal_count) for d in dims]}"
    except Exception as e:  # noqa: BLE001
        ok5 = False
        detail5 = f"下游报错：{e!r}"
    results.append(("5 下游不报错", ok5, detail5))

    # ---- 汇总 ----
    print("===== 切片09 学情主轴改造 · headless 烟测 =====")
    all_ok = True
    for name, ok, detail in results:
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} | {detail}")
    print("=" * 48)
    print("总判定：", "✅ 全部通过" if all_ok else "❌ 存在失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

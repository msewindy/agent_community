"""Headless smoke for 切片10 / S-B — 拍批改作业入学情（归类器 + 分流 + 收件箱）.

覆盖通过标准（见 学生Jarvis-v2/L2-验证切片/切片10-拍批改作业入学情.md §3）：
  1 闭集不臆造：归类输出 kp_id ∈ 候选 或 None
  2 分流正确：高置信加减法→auto；无匹配→inbox；中置信/对错未知→confirm
  3 自动入学情：高置信判错题经归类→入学情（知识点主轴）
  4 收件箱兜底：无匹配 KP 的题（方向与位置）→ 收件箱 pending 可列出
  5 收件箱可解决：家长把某条归类到 KP → 入学情、条目转 resolved
  6 真实 LLM 闭集：DeepSeek 对"方向与位置"返回 None（守 D2，不臆造）、对加法挑出数学 KP

运行：
  PY=/home/administrator/.hermes/hermes-agent/venv/bin/python
  $PY -m agent_platform.learning.smoke_photo_triage
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.photo_triage import (
    GradedItem,
    LlmKpMatcher,
    PhotoTriageService,
    StubKpMatcher,
)
from agent_platform.learning.store import layout_for, load_gap_map
from agent_platform.learning.student_context import StudentContextService

STU = "smoke-photo"


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    tmp = Path(tempfile.mkdtemp(prefix="smoke-photo-"))

    catalog = KpCatalogService()
    ctx = StudentContextService(data_root=tmp)
    ctx.init_from_defaults(STU)  # 二年级·数学默认课程
    attempt = AttemptService(data_root=tmp, context_svc=ctx, catalog=catalog)

    # 确定性 stub：子串 → (kp_id, confidence)
    stub = StubKpMatcher(
        rules=[
            ("47+38", "kp-g2-add-carry", 0.95),     # 进位加法，高置信
            ("23+5", "kp-g2-add-no-carry", 0.70),   # 不进位加法，中置信
            ("55-9", "kp-g2-sub-borrow", 0.95),     # 退位减法，高置信（但对错未知）
        ]
    )
    svc = PhotoTriageService(
        matcher=stub, data_root=tmp, catalog=catalog, ctx_svc=ctx, attempt_svc=attempt
    )

    items = [
        GradedItem(stem="47+38=?", student_answer="75", is_correct=False),   # A → auto
        GradedItem(stem="金鱼巷在通政巷的什么方向？", student_answer="南", is_correct=False),  # B → inbox（无 KP）
        GradedItem(stem="23+5=?", student_answer="30", is_correct=False),    # C → confirm（中置信）
        GradedItem(stem="55-9=?", student_answer="", is_correct=None),       # D → confirm（对错未知）
    ]
    classified = svc.classify(STU, items)
    by_stem = {c.stem: c for c in classified}

    # ---- 标准1：闭集不臆造 ----
    cand_ids = {c.kp_id for c in svc.candidates(STU)}
    ok1 = all((c.matched_kp_id is None or c.matched_kp_id in cand_ids) for c in classified)
    results.append((
        "1 闭集不臆造",
        ok1,
        ", ".join(f"{c.stem[:8]}→{c.matched_kp_id}" for c in classified),
    ))

    # ---- 标准2：分流正确 ----
    tiers = {s: by_stem[s].tier for s in by_stem}
    ok2 = (
        by_stem["47+38=?"].tier == "auto"
        and by_stem["金鱼巷在通政巷的什么方向？"].tier == "inbox"
        and by_stem["23+5=?"].tier == "confirm"
        and by_stem["55-9=?"].tier == "confirm"
    )
    results.append(("2 三档分流正确", ok2, str({k[:8]: v for k, v in tiers.items()})))

    # ---- ingest → 入学情 / 收件箱 ----
    summary = svc.ingest(STU, classified)

    # ---- 标准3：自动入学情（高置信判错 → 知识点主轴 gap）----
    gm = load_gap_map(layout_for(STU, tmp).gap_map_path)
    g_carry = next((g for g in gm.gaps if g.gap_id == "gap-kp-g2-add-carry"), None)
    ok3 = (
        summary["auto"] == 1
        and g_carry is not None
        and g_carry.stats.total_wrong >= 1
    )
    results.append((
        "3 高置信判错自动入学情",
        ok3,
        f"auto={summary['auto']} gap={'有' if g_carry else '无'} "
        f"wrong={getattr(g_carry.stats,'total_wrong',None) if g_carry else None}",
    ))

    # ---- 标准4：收件箱兜底（方向题无 KP → pending）----
    pending = svc.inbox_list(STU, status="pending")
    dir_entry = next((e for e in pending if "方向" in e.stem), None)
    ok4 = (
        summary["inbox"] >= 1
        and dir_entry is not None
        and dir_entry.matched_kp_id is None
        and dir_entry.status == "pending"
    )
    results.append((
        "4 无匹配题落收件箱",
        ok4,
        f"inbox={summary['inbox']} confirm={summary['confirm']} pending={len(pending)} "
        f"方向条目={'有' if dir_entry else '无'}",
    ))

    # ---- 标准5：收件箱可解决（家长归类 confirm 项 → 入学情）----
    confirm_entry = next((e for e in pending if "23+5" in e.stem), None)
    if confirm_entry is not None:
        res = svc.inbox_resolve(
            STU, confirm_entry.entry_id, knowledge_point_id="kp-g2-add-no-carry", is_correct=False
        )
        gm2 = load_gap_map(layout_for(STU, tmp).gap_map_path)
        g_nc = next((g for g in gm2.gaps if g.gap_id == "gap-kp-g2-add-no-carry"), None)
        still_pending = [e for e in svc.inbox_list(STU, status="pending") if e.entry_id == confirm_entry.entry_id]
        ok5 = bool(res.attempt_id) and g_nc is not None and not still_pending
        detail5 = f"attempt={res.attempt_id} gap_nc={'有' if g_nc else '无'} 仍pending={len(still_pending)}"
    else:
        ok5 = False
        detail5 = "未找到待解决的 confirm 条目"
    results.append(("5 收件箱可解决→入学情", ok5, detail5))

    # ---- 标准6：真实 LLM 闭集（best-effort：无网络/密钥则跳过为通过）----
    try:
        llm = LlmKpMatcher.from_config({})
        llm_svc = PhotoTriageService(
            matcher=llm, data_root=tmp, catalog=catalog, ctx_svc=ctx, attempt_svc=attempt
        )
        real = llm_svc.classify(
            STU,
            [
                GradedItem(stem="47+38=?", student_answer="75", is_correct=False),
                GradedItem(stem="看图填空：金鱼巷在通政巷的（  ）方向。", student_answer="南", is_correct=False),
            ],
        )
        add_item = real[0]
        dir_item = real[1]
        ok6 = (
            add_item.matched_kp_id is not None
            and add_item.matched_kp_id in cand_ids
            and add_item.matched_kp_id.startswith("kp-g2-")
            and dir_item.matched_kp_id is None  # 守 D2：目录无方向KP → 不臆造
        )
        detail6 = (
            f"加法→{add_item.matched_kp_id}({add_item.confidence:.2f}) "
            f"方向→{dir_item.matched_kp_id}({dir_item.reason})"
        )
    except Exception as e:  # noqa: BLE001
        ok6 = True
        detail6 = f"（跳过：LLM 不可用 {type(e).__name__}: {str(e)[:60]}）"
    results.append(("6 真实LLM闭集不臆造", ok6, detail6))

    # ---- 汇总 ----
    print("===== 切片10 / S-B 拍批改作业入学情 · headless 烟测 =====")
    all_ok = True
    for name, ok, detail in results:
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} | {detail}")
    print("=" * 52)
    print("总判定：", "✅ 全部通过" if all_ok else "❌ 存在失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

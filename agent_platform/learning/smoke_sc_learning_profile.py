"""Headless smoke for 切片11 / S-C — 学情统一视图 + 拍照 Agent 编排."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.learning_profile import LearningProfileService
from agent_platform.learning.photo_triage import (
    ClassifiedItem,
    GradedItem,
    PhotoTriageService,
    StubKpMatcher,
)
from agent_platform.learning.store import layout_for, load_attempt
from agent_platform.learning.student_context import StudentContextService

STU = "smoke-sc"


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    tmp = Path(tempfile.mkdtemp(prefix="smoke-sc-"))
    catalog = KpCatalogService()
    ctx = StudentContextService(data_root=tmp)
    ctx.init_from_defaults(STU)
    attempt = AttemptService(data_root=tmp, context_svc=ctx, catalog=catalog)
    stub = StubKpMatcher([("47+38", "kp-g2-add-carry", 0.95)])
    triage = PhotoTriageService(
        matcher=stub, data_root=tmp, catalog=catalog, ctx_svc=ctx, attempt_svc=attempt
    )
    profile = LearningProfileService(data_root=tmp, triage_svc=triage, catalog=catalog)

    # 模拟 Agent 调 classify_photo：高置信错题 auto + 无匹配题 inbox
    items = [
        GradedItem(stem="47+38=?", student_answer="75", is_correct=False),
        GradedItem(stem="金鱼巷在通政巷的什么方向？", student_answer="南", is_correct=False),
    ]
    classified = triage.classify(STU, items)
    triage.ingest(STU, classified)

    prof = profile.get_profile(STU)
    ok1 = len(prof.gaps) >= 1 and len(prof.pending_items) >= 1
    results.append((
        "1 学情统一视图 gaps+pending",
        ok1,
        f"gaps={len(prof.gaps)} pending={len(prof.pending_items)}",
    ))

    pending = prof.pending_items[0]
    res = triage.inbox_resolve(
        STU, pending.entry_id, knowledge_point_id="kp-g2-add-no-carry", is_correct=False
    )
    att = load_attempt(layout_for(STU, tmp).attempt_path(res.attempt_id))
    ok2 = att.source == "photo_manual"
    results.append(("2 家长归类 source=photo_manual", ok2, f"source={att.source}"))

    auto_att = None
    for p in layout_for(STU, tmp).attempts_dir.glob("att-*.json"):
        a = load_attempt(p)
        if a.source == "photo_auto":
            auto_att = a
            break
    ok3 = auto_att is not None
    results.append(("3 自动入学情 source=photo_auto", ok3, f"found={auto_att is not None}"))

    # classify_photo handler（注入 stub matcher，避免烟测依赖 API key）
    try:
        import agent_platform.integrations.hermes.student_tools as st

        st._triage_svc = triage
        out = st.classify_photo(
            {
                "items": [
                    {"stem": "23+5=?", "student_answer": "30", "is_correct": False},
                ]
            },
            student_id=STU,
        )
        ok4 = '"success": true' in out.lower() or '"success":true' in out.replace(" ", "")
        results.append(("4 classify_photo 工具可调用", ok4, out[:160]))
    except Exception as e:  # noqa: BLE001
        results.append(("4 classify_photo 工具可调用", False, repr(e)))

    print("===== 切片11 / S-C headless 烟测 =====")
    all_ok = True
    for name, ok, detail in results:
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} | {detail}")
    print("=" * 44)
    print("总判定：", "✅ 全部通过" if all_ok else "❌ 存在失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

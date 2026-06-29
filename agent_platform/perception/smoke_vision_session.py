"""Headless smoke for 切片12 — vision session + pre_llm block（无 VLM 调用）."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from agent_platform.perception.vision_session import VISION_ID_ENV, VisionSessionStore
from agent_platform.perception.vision_understand import (
    VisionItem,
    VisionUnderstandResult,
    format_vision_pre_llm_block,
    parse_vlm_understand_json,
)


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    sample = json.dumps(
        {
            "image_type": "graded_homework",
            "summary": "数学口算卷",
            "items": [
                {"stem": "50-18=?", "student_answer": "42", "is_correct": False, "teacher_mark": "✗"},
            ],
        },
        ensure_ascii=False,
    )
    parsed = parse_vlm_understand_json(sample)
    ok1 = parsed.get("image_type") == "graded_homework"
    results.append(("1 JSON 解析", ok1, str(parsed.get("image_type"))))

    rec = VisionUnderstandResult(
        vision_id="",
        image_type="graded_homework",
        summary="测试",
        items=[VisionItem(stem="50-18=?", student_answer="42", is_correct=False)],
    )
    store = VisionSessionStore()
    saved = store.save(rec)
    loaded = store.get(saved.vision_id)
    ok2 = loaded is not None and loaded.stats["wrong"] == 1
    results.append(("2 session 存取", ok2, f"id={saved.vision_id} wrong={loaded.stats if loaded else None}"))

    block = format_vision_pre_llm_block(saved)
    ok3 = (
        "classify_photo" in block
        and "50-18" in block
        and "入库" in block
        and "口播" in block
        and "语义意图" in block
    )
    results.append(("3 pre_llm 块含入库/口播分层", ok3, block[:100].replace("\n", " ")))

    os.environ[VISION_ID_ENV] = saved.vision_id
    from_env = VisionSessionStore.load_from_env()
    ok4 = from_env is not None and from_env.vision_id == saved.vision_id
    results.append(("4 env 加载 vision", ok4, from_env.vision_id if from_env else "none"))
    os.environ.pop(VISION_ID_ENV, None)

    print("===== 切片12 vision 链路 · headless 烟测 =====")
    all_ok = True
    for name, ok, detail in results:
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} | {detail}")
    print("=" * 44)
    print("总判定：", "✅ 全部通过" if all_ok else "❌ 存在失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""切片08/12 — 图像「理解」headless 验证（已批改作业等多意图）。

用法：
    PY=/home/administrator/.hermes/hermes-agent/venv/bin/python
    $PY -m agent_platform.perception.smoke_vlm_understand <图片路径> [更多图片...]
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ENV = Path(os.path.expanduser("~/.hermes/.env"))
if _ENV.is_file():
    for _line in _ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from agent_platform.perception.vision_session import VisionSessionStore
from agent_platform.perception.vision_understand import understand_image


def main() -> int:
    images = [Path(p) for p in sys.argv[1:]]
    if not images:
        print("用法: python -m agent_platform.perception.smoke_vlm_understand <图片路径> [...]")
        return 2

    store = VisionSessionStore()
    ok = 0
    for img in images:
        if not img.is_file():
            print(f"❌ 找不到文件: {img}\n")
            continue
        print(f"===== {img.name} =====")
        t0 = time.time()
        try:
            result = understand_image(img)
            saved = store.save(result, image_copy_from=img)
            dt = round(time.time() - t0, 1)
            print(f"[{dt}s] vision_id={saved.vision_id}")
            print(f"image_type = {saved.image_type}")
            print(f"card: {saved.card_title} | {saved.card_subtitle}")
            print(f"stats: {saved.stats}")
            for i, it in enumerate(saved.items[:8], 1):
                mark = {True: '✓', False: '✗', None: '?'}[it.is_correct]
                print(f"  {i}. [{mark}] {it.stem[:40]} → {it.student_answer}")
            if len(saved.items) > 8:
                print(f"  ... +{len(saved.items)-8} more")
            print()
            ok += 1
        except Exception as e:
            print(f"❌ 调用失败: {type(e).__name__}: {str(e)[:300]}\n")

    print(f"完成：{ok}/{len(images)} 张。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

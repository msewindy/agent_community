#!/usr/bin/env python3
"""切片05 — 拍照识题 headless 验证。

用 VLM（DashScope Qwen-VL）以「抄出题目原文」模式转写真实作业照片，
人工比对准确率，决定是否值得接进聊天入口。

用法：
    PY=/home/administrator/.hermes/hermes-agent/venv/bin/python
    $PY -m agent_platform.perception.smoke_ocr_homework <图片路径> [更多图片...]

前置：在 ~/.hermes/.env 配 DASHSCOPE_API_KEY；perception.yaml 的 vision.provider
会被本脚本临时覆盖为 openai_compatible（不改全局配置）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 从 ~/.hermes/.env 兜底加载 DASHSCOPE_API_KEY（若环境未注入）
_ENV = Path(os.path.expanduser("~/.hermes/.env"))
if _ENV.is_file():
    for _line in _ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from agent_platform.perception._config import load_perception_config  # noqa: E402
from agent_platform.perception.vlm import build_vlm_adapter  # noqa: E402

TRANSCRIBE_Q = (
    "这是一张小学作业照片。请把图片里的题目【原文一字不差地】抄写出来，"
    "保留数字、运算符号和题号；如果有多道题，每道题单独一行。"
    "只输出题目本身，不要解答、不要解释。看不清的字用□代替。"
)


def main() -> int:
    images = [Path(p) for p in sys.argv[1:]]
    if not images:
        print("用法: python -m agent_platform.perception.smoke_ocr_homework <图片路径> [...]")
        return 2

    cfg = load_perception_config()
    vision = dict(cfg.get("vision") or {})
    vision["provider"] = "openai_compatible"  # 临时覆盖，不改全局
    vision.setdefault("model", "qwen-vl-max")
    vision.setdefault("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vision.setdefault("api_key_env", "DASHSCOPE_API_KEY")
    adapter = build_vlm_adapter({"vision": vision})

    print(f"provider={adapter.provider} model={adapter.model}")
    print(f"key_present={bool(os.environ.get(vision['api_key_env']))}\n")

    ok = 0
    for img in images:
        if not img.is_file():
            print(f"❌ 找不到文件: {img}\n")
            continue
        print(f"===== {img.name} =====")
        t0 = time.time()
        try:
            text = adapter.describe(img, TRANSCRIBE_Q)
            dt = round(time.time() - t0, 1)
            print(f"[{dt}s] 转写结果：\n{text}\n")
            ok += 1
        except Exception as e:
            print(f"❌ 调用失败: {type(e).__name__}: {str(e)[:300]}\n")

    print(f"完成：{ok}/{len(images)} 张成功转写。请人工比对数字/运算符准确率。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

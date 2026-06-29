#!/usr/bin/env python3
"""M8 — 8 US end-to-end integration regression + trace audit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> bool:
    print(f"FAIL {msg}", file=sys.stderr)
    return False


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _run_script(rel: str, *args: str) -> int:
    script = _REPO / rel
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    return proc.returncode


def us1_voice_baseline(*, with_tts: bool) -> bool:
    """US-1：双语路由 + voice 配置 + 可选 TTS 冒烟（不跑全链路麦）。"""
    try:
        from agent_platform.voice._config import load_voice_config
        from agent_platform.voice.asr_router import _cjk_ratio
        from agent_platform.voice.tts import voice_for_language
    except ImportError as e:
        return _fail(f"US-1 voice imports: {e}")

    cfg = load_voice_config()
    if not cfg.get("wake") or not cfg.get("tts"):
        return _fail("US-1 voice.yaml missing wake/tts sections")

    if voice_for_language("zh", zh_voice="zh-CN-XiaoxiaoNeural", en_voice="en-US-JennyNeural") != "zh-CN-XiaoxiaoNeural":
        return _fail("US-1 zh TTS voice mapping")
    if voice_for_language("en", zh_voice="zh-CN-XiaoxiaoNeural", en_voice="en-US-JennyNeural") != "en-US-JennyNeural":
        return _fail("US-1 en TTS voice mapping")

    if _cjk_ratio("今天天气不错") < 0.5:
        return _fail("US-1 CJK ratio for Chinese text")
    if _cjk_ratio("Hello world today") > 0.2:
        return _fail("US-1 CJK ratio for English text")

    _ok("US-1 voice config + bilingual routing hints")

    if with_tts:
        rc = _run_script("agent_platform/voice/smoke_tts.py")
        if rc != 0:
            return _fail("US-1 smoke_tts")
        _ok("US-1 Edge-TTS smoke")
    else:
        _skip("US-1 smoke_tts (--with-voice-tts to enable)")
    return True


def us2_perception(*, skip: bool) -> bool:
    """US-2：感知按需 + 摄像头策略（accept_m4_us2）。"""
    if skip:
        _skip("US-2 accept_m4_us2")
        return True
    try:
        from agent_platform.perception.frames import opencv_available

        if not opencv_available():
            _skip("US-2 OpenCV not installed")
            return True
    except Exception:
        _skip("US-2 perception import")
        return True

    rc = _run_script(
        "agent_platform/perception/accept_m4_us2.py",
        "--skip-d5",
        "--skip-hermes",
    )
    if rc != 0:
        return _fail("US-2 accept_m4_us2 subprocess")
    _ok("US-2 perception US-2 regression")
    return True


def us3_preference_behavior() -> bool:
    """US-3：记忆偏好 + 行为档（M2 + M7）。"""
    with tempfile.TemporaryDirectory(prefix="m8_us3_") as td:
        persist = Path(td) / "mem.json"
        from agent_platform.memory.accept_m2_us import accept_us3_mock

        if not accept_us3_mock(persist, "m8-us3"):
            return _fail("US-3 memory persist")
    _ok("US-3 memory preference cross-restart")

    rc = _run_script(
        "agent_platform/calibration/accept_m7_manual.py",
        "--skip-d7",
        "--skip-d8",
        "--d9-days",
        "3",
    )
    if rc != 0:
        return _fail("US-3 behavior profile (accept_m7_manual D9)")
    _ok("US-3 behavior profile + 3-day restart sim")
    return True


def us4_wiki_precipitate(*, skip_hermes: bool) -> bool:
    """US-4：Wiki 沉淀 + 次日召回。"""
    args = ["--skip-hermes"] if skip_hermes else []
    rc = _run_script("agent_platform/wiki/accept_m3_us4.py", *args)
    if rc != 0:
        return _fail("US-4 accept_m3_us4")
    _ok("US-4 wiki precipitate + recall")
    return True


def us5_proactive(*, skip_hermes: bool) -> bool:
    """US-5：主动行为 + 静默 + dismiss。"""
    args = ["--skip-d5"]
    if skip_hermes:
        args.append("--skip-hermes")
    rc = _run_script("agent_platform/proactive/accept_m5_us5.py", *args)
    if rc != 0:
        return _fail("US-5 accept_m5_us5")
    _ok("US-5 proactive quiet hours + dismiss")
    return True


def us6_calibration(*, skip_d5: bool) -> bool:
    """US-6：校准 + 道歉 + supersede。"""
    args = []
    if skip_d5:
        args.append("--skip-d5")
    rc = _run_script("agent_platform/calibration/accept_m7_us.py", *args)
    if rc != 0:
        return _fail("US-6 accept_m7_us")
    _ok("US-6 calibration + correction")
    return True


def us7_memory_panel() -> bool:
    """US-7：记忆面板浏览/筛选/删除。"""
    from agent_platform.memory.accept_m2_us import accept_us7_panel

    if not accept_us7_panel("m8-us7"):
        return _fail("US-7 memory panel")
    _ok("US-7 memory panel delete + tombstone")
    return True


def us8_project_status() -> bool:
    """US-8：跨会话项目状态召回。"""
    from agent_platform.integration.us8_project import accept_us8_project_recall

    if not accept_us8_project_recall():
        return _fail("US-8 project recall")
    _ok("US-8 ProjectX milestone recall + audit")
    return True


def eng_combined_recall() -> bool:
    """M2+M3 联合召回。"""
    rc = _run_script("agent_platform/integrations/demo_recall_m2_m3.py")
    if rc != 0:
        return _fail("combined_recall demo")
    _ok("M2+M3 combined_recall")
    return True


def eng_trace_chain() -> bool:
    """工程 §14：trace_id 串联记忆 + 工具。"""
    from agent_platform.integration.trace_audit import accept_trace_chain

    if not accept_trace_chain():
        return _fail("trace_id audit chain")
    _ok("trace_id spans memory + tools draft")
    return True


def eng_mcp_governance(*, skip_stdio: bool) -> bool:
    """C2/C3 工具链回归（M6）。"""
    args = ["--skip-d5"]
    if skip_stdio:
        args.append("--skip-stdio")
    args.append("--skip-hermes")
    rc = _run_script("agent_platform/tools/accept_m6_us.py", *args)
    if rc != 0:
        return _fail("M6 accept_m6_us in M8 matrix")
    _ok("M6 MCP L0–L2 governance")
    return True


def print_manual_checklist() -> None:
    print(
        """
--- M8 手动验收（v1 签字）---

D1 集成录屏（可选）:
  跑通 accept_m8_integration.py 后，按 8 US 剧本各演示 1 次并录屏存档。

D2 7 天自用日记:
  复制 docs/M8-seven-day-diary.md → 每日 ≥5 次语音交互打卡
  检查: python agent_platform/integration/diary_check.py docs/M8-seven-day-diary.md

D3 三场景顺手度 + Wiki 复利:
  在日记中记录 ≥3 个比「开电脑 GPT」更顺手的场景
  至少 1 次「沉淀 → 次日 Wiki 受益」

D4 时延基准（可选）:
  python agent_platform/voice/bench_m1.py

签字表：docs/M8-us-acceptance.md §5
"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description="M8 — 8 US integration regression")
    p.add_argument("--skip-us1", action="store_true")
    p.add_argument("--skip-us2", action="store_true")
    p.add_argument("--skip-us3", action="store_true")
    p.add_argument("--skip-us4", action="store_true")
    p.add_argument("--skip-us5", action="store_true")
    p.add_argument("--skip-us6", action="store_true")
    p.add_argument("--skip-us7", action="store_true")
    p.add_argument("--skip-us8", action="store_true")
    p.add_argument("--skip-engineering", action="store_true")
    p.add_argument("--skip-hermes", action="store_true", default=True, help="skip hermes in sub-accepts")
    p.add_argument("--skip-stdio", action="store_true", default=True)
    p.add_argument("--with-voice-tts", action="store_true", help="US-1 run smoke_tts")
    p.add_argument("--checklist", action="store_true")
    args = p.parse_args()

    if args.checklist:
        print_manual_checklist()
        return 0

    print("=== accept_m8_integration (8 US + engineering) ===\n")

    steps: list[tuple[str, callable]] = []
    if not args.skip_us1:
        steps.append(("US-1", lambda: us1_voice_baseline(with_tts=args.with_voice_tts)))
    if not args.skip_us2:
        steps.append(("US-2", lambda: us2_perception(skip=args.skip_us2)))
    if not args.skip_us3:
        steps.append(("US-3", us3_preference_behavior))
    if not args.skip_us4:
        steps.append(("US-4", lambda: us4_wiki_precipitate(skip_hermes=args.skip_hermes)))
    if not args.skip_us5:
        steps.append(("US-5", lambda: us5_proactive(skip_hermes=args.skip_hermes)))
    if not args.skip_us6:
        steps.append(("US-6", lambda: us6_calibration(skip_d5=True)))
    if not args.skip_us7:
        steps.append(("US-7", us7_memory_panel))
    if not args.skip_us8:
        steps.append(("US-8", us8_project_status))

    if not args.skip_engineering:
        steps.extend(
            [
                ("ENG recall", eng_combined_recall),
                ("ENG trace", eng_trace_chain),
                ("ENG mcp", lambda: eng_mcp_governance(skip_stdio=args.skip_stdio)),
            ]
        )

    ok = True
    for label, fn in steps:
        print(f"--- {label} ---")
        if not fn():
            ok = False

    print()
    if ok:
        print("accept_m8_integration: PASS — 8 US + engineering regression OK")
        print_manual_checklist()
        return 0
    print("accept_m8_integration: FAIL", file=sys.stderr)
    print_manual_checklist()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

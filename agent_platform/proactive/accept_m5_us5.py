#!/usr/bin/env python3
"""M5 D6–D10 — US-5 formal acceptance (mock memory + optional Hermes / Voice)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_CLI = _REPO / "agent_platform" / "proactive" / "cli_proactive.py"
_BREAK_SNIPPET = "休息"
_DISMISS = "我在做正事，别打扰"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> bool:
    print(f"FAIL {msg}", file=sys.stderr)
    return False


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _isolated_root() -> Path:
    td = tempfile.mkdtemp(prefix="us5_")
    root = Path(td) / "proactive"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proactive_cfg(root: Path, *, quiet: bool = True) -> dict:
    q = (
        {"enabled": True, "start": "22:00", "end": "07:00", "timezone": "UTC"}
        if quiet
        else {"enabled": False}
    )
    return {
        "enabled": True,
        "level": "L0",
        "quiet_hours": q,
        "triggers": {
            "work_break": {
                "enabled": True,
                "work_minutes_threshold": 120,
                "message": "已经 2 小时了，要不要休息一下？",
            }
        },
        "session": {"snooze_rest_of_session": True},
        "memory": {
            "write_dismiss_preference": True,
            "dedup_enabled": True,
            "dismiss_template": "用户不希望主动提醒",
        },
        "store": {"root": str(root)},
    }


def _make_svc(root: Path, *, quiet: bool = True):
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService
    from agent_platform.proactive.service import ProactiveService

    mem = MemoryService(
        adapter=MockMemAdapter(),
        config={"backend": "mock", "gate": {"enabled": False}},
    )
    return ProactiveService(
        config=_proactive_cfg(root, quiet=quiet),
        store_root=root,
        memory_service=mem,
    ), mem


def us5_a1_work_break(root: Path | None = None) -> bool:
    """US-5 场景 1：连续工作 ≥2h → 休息提醒。"""
    from agent_platform.proactive.contracts import ProactiveEvaluateRequest

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=False)
    r = svc.evaluate(
        ProactiveEvaluateRequest(
            session_id="us5-a1",
            work_minutes=125,
            natural_pause=True,
        )
    )
    if not r.allowed or not r.proposal:
        return _fail(f"US-5 A1: expected proposal, got {r}")
    if _BREAK_SNIPPET not in r.proposal.message:
        return _fail(f"US-5 A1: missing break message: {r.proposal.message!r}")
    _ok("US-5 A1 work_break — 连续 2h → 休息提醒")
    return True


def us5_a2_dismiss_snooze(root: Path | None = None) -> bool:
    """US-5 场景 2：别打扰 → 本会话静默。"""
    from agent_platform.proactive.contracts import (
        ProactiveEvaluateRequest,
        ProactiveFeedbackRequest,
    )

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=False)
    fb = svc.record_feedback(
        ProactiveFeedbackRequest(session_id="us5-a2", user_message=_DISMISS)
    )
    if not fb.dismissed or not fb.session_snoozed:
        return _fail(f"US-5 A2: dismiss snooze failed {fb}")
    after = svc.evaluate(
        ProactiveEvaluateRequest(
            session_id="us5-a2",
            work_minutes=200,
            natural_pause=True,
        )
    )
    if after.allowed or after.reason_code != "session_snoozed":
        return _fail(f"US-5 A2: should block after snooze: {after}")
    _ok("US-5 A2 dismiss → session_snoozed + evaluate blocked")
    return True


def us5_a3_quiet_hours(root: Path | None = None) -> bool:
    """US-5 场景 3：22:00–7:00 静默时段硬拒绝。"""
    from agent_platform.proactive.contracts import ProactiveEvaluateRequest

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=True)
    r = svc.evaluate(
        ProactiveEvaluateRequest(
            session_id="us5-a3",
            work_minutes=300,
            natural_pause=True,
            now=datetime(2026, 5, 20, 23, 0, tzinfo=ZoneInfo("UTC")),
        )
    )
    if r.allowed or r.reason_code != "quiet_hours":
        return _fail(f"US-5 A3: expected quiet_hours block, got {r}")
    _ok("US-5 A3 quiet_hours — 23:00 UTC 不主动发声")
    return True


def us5_a4_memory_persist(root: Path | None = None) -> bool:
    """US-5：dismiss 偏好写入记忆（subject_key）。"""
    from agent_platform.proactive.contracts import ProactiveFeedbackRequest
    from agent_platform.proactive.memory_feedback import DISMISS_SUBJECT_KEY

    root = root or _isolated_root()
    svc, mem = _make_svc(root, quiet=False)
    fb = svc.record_feedback(
        ProactiveFeedbackRequest(session_id="us5-a4", user_message="别打扰")
    )
    if not fb.memory_written or not fb.memory_record_id:
        return _fail(f"US-5 A4: memory not written {fb}")
    hits = mem.search("别打扰", device_id=mem.default_device_id, limit=5)
    if not hits.hits:
        return _fail("US-5 A4: memory search empty after write")
    meta = hits.hits[0].metadata or {}
    if meta.get("subject_key") != DISMISS_SUBJECT_KEY:
        return _fail(f"US-5 A4: subject_key={meta.get('subject_key')}")
    _ok("US-5 A4 memory persist — proactive.do_not_disturb")
    return True


def us5_a5_memory_dedup(root: Path | None = None) -> bool:
    """US-5：重复 dismiss 记忆去重。"""
    from agent_platform.proactive.contracts import ProactiveFeedbackRequest

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=False)
    svc.record_feedback(
        ProactiveFeedbackRequest(session_id="us5-a5a", user_message="别打扰")
    )
    fb2 = svc.record_feedback(
        ProactiveFeedbackRequest(session_id="us5-a5b", user_message="不要打扰我")
    )
    if not fb2.memory_deduped:
        return _fail(f"US-5 A5: expected dedup {fb2}")
    _ok("US-5 A5 memory dedup — second dismiss skipped")
    return True


def us5_a6_hermes_tools(root: Path | None = None) -> bool:
    """US-5：Hermes agent_proactive_* 工具链。"""
    try:
        from agent_platform.integrations.hermes import proactive_tools as pt
    except ImportError as e:
        _skip(f"US-5 A6 hermes tools: {e}")
        return True

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=False)
    pt._get_proactive_service = lambda: svc  # type: ignore[method-assign]

    st = json.loads(pt.agent_proactive_status({}, current_session_id="us5-a6"))
    if not st.get("success"):
        return _fail(f"US-5 A6 status: {st}")

    ev = json.loads(
        pt.agent_proactive_evaluate(
            {"work_minutes": 130},
            current_session_id="us5-a6",
        )
    )
    if not ev.get("allowed") or _BREAK_SNIPPET not in (ev.get("proposal") or ""):
        return _fail(f"US-5 A6 evaluate: {ev}")

    fb = json.loads(
        pt.agent_proactive_feedback(
            {"message": _DISMISS},
            current_session_id="us5-a6",
        )
    )
    if not fb.get("session_snoozed"):
        return _fail(f"US-5 A6 feedback: {fb}")

    ev2 = json.loads(
        pt.agent_proactive_evaluate(
            {"work_minutes": 200},
            current_session_id="us5-a6",
        )
    )
    if ev2.get("allowed") or ev2.get("reason_code") != "session_snoozed":
        return _fail(f"US-5 A6 post-snooze evaluate: {ev2}")

    _ok("US-5 A6 Hermes agent_proactive_* status/evaluate/feedback")
    return True


def us5_a7_voice_bridge(root: Path | None = None) -> bool:
    """US-5：VoiceProactiveBridge dismiss / 工时 / snooze 后阻断。"""
    from agent_platform.voice.proactive_bridge import VoiceProactiveBridge

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=False)
    bridge = VoiceProactiveBridge(
        nudge_after_work_report=True,
        service=svc,
    )

    dismiss = bridge.on_user_message(_DISMISS, session_id="us5-v1")
    if not dismiss.reply_override or "打扰" not in dismiss.reply_override:
        return _fail(f"US-5 A7 dismiss override: {dismiss.reply_override!r}")

    blocked = bridge.maybe_proactive_nudge(session_id="us5-v1", work_minutes=200)
    if blocked.proactive_allowed:
        return _fail("US-5 A7: nudge should be blocked after snooze")

    work = bridge.on_user_message("我连续工作了2小时", session_id="us5-v2")
    if work.work_minutes_reported != 120.0:
        return _fail(f"US-5 A7 work minutes: {work.work_minutes_reported}")
    if not work.reply_override or _BREAK_SNIPPET not in work.reply_override:
        return _fail("US-5 A7: nudge after work report missing")

    _ok("US-5 A7 VoiceProactiveBridge dismiss + work nudge + snooze block")
    return True


def us5_a8_event_log(root: Path | None = None) -> bool:
    """US-5：events.log.md + sessions/*.json 可追溯。"""
    from agent_platform.proactive.contracts import (
        ProactiveEvaluateRequest,
        ProactiveFeedbackRequest,
    )

    root = root or _isolated_root()
    svc, _ = _make_svc(root, quiet=False)
    svc.evaluate(
        ProactiveEvaluateRequest(session_id="us5-a8", work_minutes=130, natural_pause=True)
    )
    svc.record_feedback(
        ProactiveFeedbackRequest(session_id="us5-a8", user_message="别打扰")
    )

    log_path = root / "events.log.md"
    if not log_path.is_file():
        return _fail("US-5 A8: events.log.md missing")
    log_text = log_path.read_text(encoding="utf-8")
    if "evaluate" not in log_text or "feedback" not in log_text:
        return _fail(f"US-5 A8: log missing lines: {log_text[-200:]}")

    sess = root / "sessions" / "us5-a8.json"
    if not sess.is_file():
        return _fail("US-5 A8: session json missing")
    data = json.loads(sess.read_text(encoding="utf-8"))
    if not data.get("snoozed"):
        return _fail(f"US-5 A8: session not snoozed {data}")
    _ok("US-5 A8 events.log.md + sessions/us5-a8.json audit")
    return True


def us5_a9_intent_parse() -> bool:
    """US-5：用户话术解析连续工时。"""
    from agent_platform.proactive.intent import parse_work_minutes_from_text

    m = parse_work_minutes_from_text("连续工作2小时")
    if m != 120.0:
        return _fail(f"US-5 A9: expected 120, got {m}")
    if parse_work_minutes_from_text("你好") is not None:
        return _fail("US-5 A9: non-work text should not parse")
    _ok("US-5 A9 intent — 连续工作2小时 → 120 min")
    return True


def us5_a10_cli_e2e(root: Path | None = None) -> bool:
    """US-5：CLI init / evaluate / feedback（--config 关闭静默以便任意时刻验收）。"""
    import yaml

    root = root or _isolated_root()
    cfg_path = root.parent / "accept_cli.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                **_proactive_cfg(root, quiet=False),
                "store": {"root": str(root)},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    env = {**__import__("os").environ, "PYTHONPATH": str(_REPO)}
    cfg_arg = ["--config", str(cfg_path)]

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(_CLI), *args],
            cwd=str(_REPO),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    r = run("init", "--root", str(root))
    if r.returncode != 0:
        return _fail(f"US-5 A10 cli init: {r.stderr}")

    r = run(
        "evaluate",
        *cfg_arg,
        "--root",
        str(root),
        "--session-id",
        "us5-cli",
        "--work-minutes",
        "125",
        "--natural-pause",
    )
    if r.returncode != 0 or "allowed=True" not in r.stdout:
        return _fail(f"US-5 A10 cli evaluate: {r.stdout}{r.stderr}")

    r = run(
        "feedback",
        *cfg_arg,
        "--root",
        str(root),
        "--session-id",
        "us5-cli",
        "--message",
        "别打扰",
    )
    if r.returncode != 0 or "snoozed=True" not in r.stdout:
        return _fail(f"US-5 A10 cli feedback: {r.stdout}{r.stderr}")

    _ok("US-5 A10 CLI init / evaluate / feedback")
    return True


def run_d5_regression(*, skip_hermes: bool) -> bool:
    from agent_platform.proactive.accept_m5_smoke import main as smoke_main

    old_argv = sys.argv
    try:
        extra = ["--skip-pytest"]
        if skip_hermes:
            extra.append("--skip-hermes")
        sys.argv = ["accept_m5_smoke", *extra]
        if smoke_main() != 0:
            return _fail("US-5 D5 regression accept_m5_smoke")
    finally:
        sys.argv = old_argv
    _ok("US-5 D5 regression accept_m5_smoke")
    return True


def print_manual_checklist() -> None:
    print(
        """
--- 手动验收清单（D7–D9，签字用）---

D7 Hermes（需 hermes + agent-proactive 插件）:
  bash agent_platform/integrations/hermes/install_plugin.sh
  hermes plugins enable agent-proactive
  hermes tools enable agent_proactive

  1. agent_proactive_evaluate work_minutes=130
     → allowed=true，proposal 含「休息」
  2. 用户：我在做正事，别打扰 → agent_proactive_feedback
     → session_snoozed=true，memory_written=true
  3. 再次 agent_proactive_evaluate → reason=session_snoozed

D8 Voice 全链路（需 Hermes + TTS 环境）:
  # voice.yaml proactive.enabled: true
  PYTHONPATH=agent_platform python agent_platform/voice/smoke_pipeline.py -t "别打扰我"
     → 应直接回复「本会话内不会…」不经 Hermes
  PYTHONPATH=agent_platform python agent_platform/voice/smoke_pipeline.py -t "我连续工作了2小时"
     → 可选 nudge_after_work_report 时播报休息提醒

D9 静默时段真机校验:
  PYTHONPATH=. python agent_platform/proactive/cli_proactive.py status
     → 查看 quiet_hours_now（本地时区）
  在 22:00–7:00 内运行 evaluate → allowed=False reason=quiet_hours

签字表：docs/M5-us-acceptance.md §5
"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description="M5 US-5 acceptance (D6–D10)")
    p.add_argument("--skip-d5", action="store_true", help="skip accept_m5_smoke regression")
    p.add_argument("--skip-hermes", action="store_true", help="skip A6 hermes tools")
    p.add_argument("--skip-cli", action="store_true", help="skip A10 CLI subprocess")
    args = p.parse_args()

    print("=== accept_m5_us5 (US-5) ===\n")

    ok = True
    steps = [
        us5_a1_work_break,
        us5_a2_dismiss_snooze,
        us5_a3_quiet_hours,
        us5_a4_memory_persist,
        us5_a5_memory_dedup,
        us5_a7_voice_bridge,
        us5_a8_event_log,
    ]
    for fn in steps:
        if not fn():
            ok = False

    if not us5_a9_intent_parse():
        ok = False

    if not args.skip_hermes and not us5_a6_hermes_tools():
        ok = False
    elif args.skip_hermes:
        _skip("US-5 A6 hermes proactive tools")

    if not args.skip_cli and not us5_a10_cli_e2e():
        ok = False
    elif args.skip_cli:
        _skip("US-5 A10 CLI e2e")

    if not args.skip_d5 and not run_d5_regression(skip_hermes=args.skip_hermes):
        ok = False
    elif args.skip_d5:
        _skip("D5 regression accept_m5_smoke")

    print()
    if ok:
        print("accept_m5_us5: PASS — US-5 automated acceptance OK")
        print_manual_checklist()
        return 0
    print("accept_m5_us5: FAIL", file=sys.stderr)
    print_manual_checklist()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

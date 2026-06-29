#!/usr/bin/env python3
"""Proactive CLI — M5 status / evaluate / feedback."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

from agent_platform.proactive._config import load_proactive_config
from agent_platform.proactive.contracts import ProactiveEvaluateRequest, ProactiveFeedbackRequest
from agent_platform.proactive.quiet_hours import in_quiet_hours
from agent_platform.proactive.service import ProactiveService
from agent_platform.proactive.store import ensure_store


def _load_cfg(config_path: Optional[Path]) -> dict:
    if config_path is None:
        return load_proactive_config()
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _svc(args: argparse.Namespace) -> ProactiveService:
    cfg = _load_cfg(getattr(args, "config", None))
    if args.root is not None:
        store = (cfg.get("store") or {}).copy()
        store["root"] = str(args.root)
        cfg = {**cfg, "store": store}
    return ProactiveService(config=cfg, store_root=args.root)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=None)
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="override proactive.yaml (e.g. acceptance with quiet_hours off)",
    )


def cmd_init(args: argparse.Namespace) -> int:
    lay = ensure_store(args.root)
    print(f"proactive store: {lay.root}")
    print(f"  sessions {lay.sessions_dir}")
    print(f"  log      {lay.events_log_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    svc = _svc(args)
    print(json.dumps(svc.status(), ensure_ascii=False, indent=2))
    cfg = svc._cfg.get("quiet_hours") or {}  # noqa: SLF001
    if cfg.get("enabled"):
        tz = cfg.get("timezone", "Asia/Shanghai")
        now = datetime.now(ZoneInfo(tz))
        in_q = in_quiet_hours(
            now,
            start=cfg.get("start", "22:00"),
            end=cfg.get("end", "07:00"),
            timezone=tz,
        )
        print(f"quiet_hours_now={in_q} local={now.isoformat()}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    svc = _svc(args)
    result = svc.evaluate(
        ProactiveEvaluateRequest(
            session_id=args.session_id,
            work_minutes=args.work_minutes,
            natural_pause=args.natural_pause,
        )
    )
    print(f"allowed={result.allowed} reason={result.reason_code}")
    if result.proposal:
        print(f"proposal: {result.proposal.message}")
    elif result.message:
        print(result.message)
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    svc = _svc(args)
    result = svc.record_feedback(
        ProactiveFeedbackRequest(
            session_id=args.session_id,
            user_message=args.message,
            write_memory=not args.no_memory,
        )
    )
    print(
        f"snoozed={result.session_snoozed} memory_written={result.memory_written} "
        f"{result.message}"
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="agent_platform proactive CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init")
    init_p.add_argument("--root", type=Path, default=None)
    init_p.set_defaults(func=cmd_init)

    st_p = sub.add_parser("status")
    _add_common(st_p)
    st_p.set_defaults(func=cmd_status)

    ev_p = sub.add_parser("evaluate")
    _add_common(ev_p)
    ev_p.add_argument("--session-id", type=str, default="cli-session")
    ev_p.add_argument("--work-minutes", type=float, default=None)
    ev_p.add_argument("--natural-pause", action="store_true")
    ev_p.set_defaults(func=cmd_evaluate)

    fb_p = sub.add_parser("feedback")
    _add_common(fb_p)
    fb_p.add_argument("--session-id", type=str, default="cli-session")
    fb_p.add_argument("--message", type=str, required=True)
    fb_p.add_argument("--no-memory", action="store_true")
    fb_p.set_defaults(func=cmd_feedback)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

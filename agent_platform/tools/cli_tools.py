#!/usr/bin/env python3
"""Tools CLI — status / invoke / drafts (M6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_platform.tools.contracts import DraftApproveRequest, DraftRejectRequest, ToolInvokeRequest
from agent_platform.tools.service import ToolService
from agent_platform.tools.store import ensure_store


def _svc(args: argparse.Namespace) -> ToolService:
    cfg = None
    if getattr(args, "config", None):
        import yaml

        with open(args.config, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    return ToolService(config=cfg, store_root=args.root)


def cmd_init(args: argparse.Namespace) -> int:
    lay = ensure_store(args.root)
    print(f"tools store: {lay.root}")
    print(f"  sandbox {lay.sandbox_root}")
    print(f"  drafts  {lay.drafts_dir}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(_svc(args).status(), ensure_ascii=False, indent=2))
    return 0


def cmd_invoke(args: argparse.Namespace) -> int:
    arguments = json.loads(args.arguments) if args.arguments else {}
    result = _svc(args).invoke(
        ToolInvokeRequest(
            server=args.server,
            tool=args.tool,
            arguments=arguments,
            session_id=args.session_id,
            draft_id=args.draft_id,
            force_execute=args.force,
        )
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status.value != "error" else 1


def cmd_drafts(args: argparse.Namespace) -> int:
    pending = _svc(args).list_pending_drafts(args.session_id)
    print(json.dumps([d.model_dump(mode="json") for d in pending], ensure_ascii=False, indent=2))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    result = _svc(args).approve_draft(
        DraftApproveRequest(draft_id=args.draft_id, session_id=args.session_id)
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status.value == "executed" else 1


def cmd_reject(args: argparse.Namespace) -> int:
    rec = _svc(args).reject_draft(DraftRejectRequest(draft_id=args.draft_id, reason=args.reason))
    print(json.dumps(rec.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="agent_platform tools / MCP CLI")
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--config", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init")
    init_p.set_defaults(func=cmd_init)

    st_p = sub.add_parser("status")
    st_p.set_defaults(func=cmd_status)

    inv_p = sub.add_parser("invoke")
    inv_p.add_argument("server")
    inv_p.add_argument("tool")
    inv_p.add_argument("--arguments", default="{}")
    inv_p.add_argument("--session-id", default="cli-session")
    inv_p.add_argument("--draft-id", default=None)
    inv_p.add_argument("--force", action="store_true")
    inv_p.set_defaults(func=cmd_invoke)

    dr_p = sub.add_parser("drafts")
    dr_p.add_argument("--session-id", default=None)
    dr_p.set_defaults(func=cmd_drafts)

    ap_p = sub.add_parser("approve")
    ap_p.add_argument("draft_id")
    ap_p.add_argument("--session-id", default=None)
    ap_p.set_defaults(func=cmd_approve)

    rej_p = sub.add_parser("reject")
    rej_p.add_argument("draft_id")
    rej_p.add_argument("--reason", default="")
    rej_p.set_defaults(func=cmd_reject)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

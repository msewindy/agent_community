#!/usr/bin/env python3
"""Perception CLI — M4 init / status / policy / capture / frames."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_platform.perception._config import resolve_store_root
from agent_platform.perception.contracts import CaptureRequest, DescribeRequest, PerceptionModality
from agent_platform.perception.service import PerceptionService
from agent_platform.perception.orchestrate import PerceptionOrchestrator
from agent_platform.perception.store import ensure_store, validate_store


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    lay = ensure_store(root)
    svc = PerceptionService(store_root=root)
    print(f"perception store: {lay.root}")
    print(f"  policy  {lay.policy_path}")
    print(f"  captures {lay.captures_dir}")
    print(f"  log     {lay.events_log_path}")
    print(f"  backend {svc.status().backend.value}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    svc = PerceptionService(store_root=args.root)
    st = svc.status()
    print(f"backend={st.backend.value} connected={st.connected} reachable={st.reachable}")
    print(f"sdk_available={st.sdk_available}")
    print(f"camera_enabled={st.camera_enabled} mic_enabled={st.microphone_enabled}")
    print(f"message: {st.message}")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    svc = PerceptionService(store_root=args.root)
    cam = None if args.camera is None else args.camera == "on"
    mic = None if args.microphone is None else args.microphone == "on"
    if args.camera is None and args.microphone is None:
        p = svc.policy
        print(f"camera_enabled={p.camera_enabled} microphone_enabled={p.microphone_enabled}")
        return 0
    pol = svc.set_policy(
        camera_enabled=cam if cam is not None else None,
        microphone_enabled=mic if mic is not None else None,
    )
    print(f"policy updated: camera={pol.camera_enabled} mic={pol.microphone_enabled}")
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    svc = PerceptionService(store_root=args.root)
    if args.enable_camera:
        svc.set_policy(camera_enabled=True)
    result = svc.capture(
        CaptureRequest(
            scene=args.scene,
            modality=PerceptionModality.vision,
            force=args.force,
            trace_id=args.trace_id or None,
        )
    )
    if not result.allowed:
        print(f"perception capture: DENIED — {result.reason_code}: {result.message}")
        return 1
    ev = result.event
    print(f"perception capture: OK trace={ev.trace_id if ev else '?'}")
    if ev:
        snippet = ev.text if len(ev.text) <= 120 else ev.text[:120] + "…"
        print(f"  text: {snippet}")
        if result.frame_path:
            print(f"  frame: {result.frame_path}")
        if result.saved_frame:
            sf = result.saved_frame
            print(f"  size: {sf.width}x{sf.height} sha256={sf.sha256[:16]}…")
    return 0


def cmd_list_frames(args: argparse.Namespace) -> int:
    svc = PerceptionService(store_root=args.root)
    frames = svc.list_frames(limit=args.limit)
    if not frames:
        print("no saved frames (run capture with camera on)")
        return 0
    for sf in frames:
        print(
            f"{sf.image_path} {sf.width}x{sf.height} "
            f"{sf.captured_at.isoformat()} backend={sf.backend}"
        )
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    svc = PerceptionService(store_root=args.root)
    if args.enable_camera:
        svc.set_policy(camera_enabled=True)
    result = svc.describe(
        DescribeRequest(
            question=args.question,
            scene=args.scene,
            force=args.force,
        )
    )
    if not result.allowed:
        print(f"perception describe: DENIED — {result.reason_code}: {result.message}")
        return 1
    print(f"perception describe: OK model={result.model} latency_ms={result.latency_ms}")
    if result.description:
        text = result.description
        snippet = text if len(text) <= 400 else text[:400] + "…"
        print(snippet)
    if result.frame_path:
        print(f"  frame: {result.frame_path}")
    return 0


def cmd_orchestrate(args: argparse.Namespace) -> int:
    svc = PerceptionService(store_root=args.root)
    if args.enable_camera:
        svc.set_policy(camera_enabled=True)
    orch = PerceptionOrchestrator(
        service=svc,
        auto_enable_camera_in_session=args.auto_camera,
    )
    turn = orch.handle_message(args.message, session_id=args.session_id)
    print(f"vision_intent={turn.vision_intent} handled={turn.handled}")
    if turn.reply_override:
        print(f"reply_override: {turn.reply_override}")
        return 0 if turn.handled else 1
    if turn.prompt_prefix:
        print("--- prompt_prefix ---")
        print(turn.prompt_prefix[:500])
    if turn.describe and turn.describe.allowed:
        print(f"describe OK model={turn.describe.model}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    missing = validate_store(root)
    if missing:
        print("perception validate: FAIL")
        for m in missing:
            print(f"  missing: {m}")
        return 1
    print(f"perception validate: OK ({root})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="agent_platform perception CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init", help="create perception_data skeleton")
    init_p.add_argument("--root", type=Path, default=None)
    init_p.set_defaults(func=cmd_init)

    st_p = sub.add_parser("status", help="probe Reachy / adapter")
    st_p.add_argument("--root", type=Path, default=None)
    st_p.set_defaults(func=cmd_status)

    pol_p = sub.add_parser("policy", help="show/set camera/mic switches")
    pol_p.add_argument("--root", type=Path, default=None)
    pol_p.add_argument("--camera", choices=["on", "off"], default=None)
    pol_p.add_argument("--microphone", choices=["on", "off"], default=None)
    pol_p.set_defaults(func=cmd_policy)

    cap_p = sub.add_parser("capture", help="capture → ObserveEvent")
    cap_p.add_argument("--scene", type=str, default="desk")
    cap_p.add_argument("--enable-camera", action="store_true")
    cap_p.add_argument("--force", action="store_true")
    cap_p.add_argument("--trace-id", type=str, default=None)
    cap_p.add_argument("--root", type=Path, default=None)
    cap_p.set_defaults(func=cmd_capture)

    val_p = sub.add_parser("validate", help="check store paths")
    val_p.add_argument("--root", type=Path, default=None)
    val_p.set_defaults(func=cmd_validate)

    lf_p = sub.add_parser("list-frames", help="list recent JPEG captures (M4 D2)")
    lf_p.add_argument("--root", type=Path, default=None)
    lf_p.add_argument("--limit", type=int, default=10)
    lf_p.set_defaults(func=cmd_list_frames)

    desc_p = sub.add_parser("describe", help="on-demand VLM Q&A (M4 D3)")
    desc_p.add_argument("--question", type=str, required=True)
    desc_p.add_argument("--scene", type=str, default="desk")
    desc_p.add_argument("--enable-camera", action="store_true")
    desc_p.add_argument("--force", action="store_true")
    desc_p.add_argument("--root", type=Path, default=None)
    desc_p.set_defaults(func=cmd_describe)

    orch_p = sub.add_parser("orchestrate", help="vision intent → describe + bus (M4 D4)")
    orch_p.add_argument("message", type=str)
    orch_p.add_argument("--session-id", type=str, default="cli-session")
    orch_p.add_argument("--enable-camera", action="store_true")
    orch_p.add_argument("--auto-camera", action="store_true", default=True)
    orch_p.add_argument("--root", type=Path, default=None)
    orch_p.set_defaults(func=cmd_orchestrate)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

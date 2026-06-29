#!/usr/bin/env python3
"""M7 D7–D9 — manual acceptance rehearsal (US-6 + US-3 后半).

Runs in-process Hermes tool handlers + live settings panel HTTP where possible.
Use for sign-off before M8; real 3-day soak remains optional follow-up (D9b).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_PANEL_HOST = "127.0.0.1"
_PANEL_PORT = 8767
_PANEL_URL = f"http://{_PANEL_HOST}:{_PANEL_PORT}/"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> bool:
    print(f"FAIL {msg}", file=sys.stderr)
    return False


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def _http_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw}


def d7_hermes_us6_conversation(*, isolated_memory: bool) -> bool:
    """D7 — US-6 对话剧本（工具链复现 Hermes 会话）。"""
    from agent_platform.integrations.hermes.calibration_tools import (
        agent_calibrate_output,
        agent_handle_correction,
    )
    from agent_platform.integrations.hermes.tools import (
        agent_memory_search,
        agent_memory_write,
        bootstrap_agent_platform,
    )
    from agent_platform.memory.service import get_memory_service

    bootstrap_agent_platform()
    if isolated_memory:
        from agent_platform.memory.adapters.mock import MockMemAdapter
        from agent_platform.memory.service import MemoryService

        get_memory_service.cache_clear()
        td = tempfile.mkdtemp(prefix="m7_d7_mem_")
        store = Path(td) / "store.json"
        mem = MemoryService(
            adapter=MockMemAdapter(persist_path=store),
            config={"backend": "mock", "gate": {"enabled": False}},
        )
        import agent_platform.memory.service as ms

        ms.get_memory_service = lambda: mem  # type: ignore[assignment]

    # 场景：此前说过版本 v0.2
    wrote = json.loads(
        agent_memory_write(
            {
                "content": "项目文档版本号是 v0.2",
                "category": "project",
                "kind": "fact",
                "subject_key": "project.doc_version",
            }
        )
    )
    if not wrote.get("success"):
        return _fail(f"D7 memory write: {wrote}")
    rid = wrote["record_id"]

    # 用户：「你之前说的那个版本号是多少来着？」→ Agent 不确定，不编造
    uncertain = json.loads(
        agent_calibrate_output(
            {
                "text": "那个版本号应该是 v0.2。",
                "confidence": 0.55,
                "has_tool_source": False,
                "memory_backed": False,
            }
        )
    )
    if uncertain.get("confidence_level") not in ("low", "medium"):
        return _fail(f"D7 should hedge uncertain guess: {uncertain}")
    if uncertain.get("confidence_level") == "low" and "不确定" not in uncertain.get("text", "") and "不太确定" not in uncertain.get("text", ""):
        return _fail(f"D7 low confidence must expose uncertainty: {uncertain.get('text')}")
    _ok("D7 step1 用户追问版本 → 低置信/不确定暴露（不编造）")

    # 可选：查证后带 source 可确定
    after_tool = json.loads(
        agent_calibrate_output(
            {
                "text": "查到了，版本号是 v0.2",
                "has_tool_source": True,
            }
        )
    )
    if after_tool.get("confidence_level") == "low":
        return _fail(f"D7 tool-backed should not stay low: {after_tool}")
    _ok("D7 step2 工具查证后 → 可确定回答")

    # 用户：「其实你之前说的是 v0.3，错了」
    corr = json.loads(
        agent_handle_correction(
            {
                "record_id": rid,
                "old_value": "v0.2",
                "new_value": "项目文档版本号是 v0.3",
            }
        )
    )
    if not corr.get("success"):
        return _fail(f"D7 correction: {corr}")
    apology = corr.get("apology_text", "")
    if "抱歉" not in apology:
        return _fail(f"D7 apology missing: {apology}")
    if any(x in apology for x in ("不过", "因为", "其实是因为")):
        return _fail(f"D7 apology must not make excuses: {apology}")
    _ok(f"D7 step3 用户纠错 → 道歉：{apology[:40]}…")

    recall = json.loads(agent_memory_search({"query": "版本", "limit": 5}))
    hits = recall.get("hits") or []
    if not any("v0.3" in (h.get("content") or "") for h in hits):
        return _fail(f"D7 recall should return v0.3: {hits}")
    if any("v0.2" in (h.get("content") or "") for h in hits):
        return _fail("D7 old v0.2 still active in search")
    _ok("D7 step4 再次询问/搜索 → v0.3，旧值已废止")
    return True


def d8_browser_settings_panel(*, live_server: bool) -> bool:
    """D8 — 设定面板 HTTP + 与 Hermes get_prompt 联动。"""
    from agent_platform.behavior._config import load_behavior_config, resolve_profile_path, resolve_store_root
    from agent_platform.behavior.service import BehaviorService
    from agent_platform.behavior.store import BehaviorStore
    from agent_platform.integrations.hermes.calibration_tools import agent_behavior_get_prompt
    from agent_platform.integrations.hermes.tools import bootstrap_agent_platform

    td = tempfile.mkdtemp(prefix="m7_d8_")
    root = Path(td)
    cfg = load_behavior_config()
    cfg = {
        **cfg,
        "store": {"root": str(root / "behavior"), "profile_file": "profile.yaml"},
        "panel": {"host": _PANEL_HOST, "port": _PANEL_PORT},
    }
    store = BehaviorStore(resolve_profile_path(cfg), default_profile=cfg.get("default_profile") or {})
    svc = BehaviorService(config=cfg, store=store)

    proc: subprocess.Popen | None = None
    env = {**os.environ, "PYTHONPATH": str(_REPO), "M7_PANEL_ROOT": str(root)}

    if live_server:
        # 独立进程启动面板（模拟用户 python -m ...）
        code = f"""
import os
from pathlib import Path
from agent_platform.api.settings_panel import create_app
from agent_platform.behavior.service import BehaviorService
from agent_platform.behavior.store import BehaviorStore
from agent_platform.behavior._config import load_behavior_config, resolve_profile_path

cfg = load_behavior_config()
root = Path(os.environ['M7_PANEL_ROOT'])
cfg['store'] = {{'root': str(root / 'behavior'), 'profile_file': 'profile.yaml'}}
cfg['panel'] = {{'host': '{_PANEL_HOST}', 'port': {_PANEL_PORT}}}
store = BehaviorStore(resolve_profile_path(cfg), default_profile=cfg.get('default_profile') or {{}})
svc = BehaviorService(config=cfg, store=store)
import uvicorn
uvicorn.run(create_app(config=cfg, service=svc), host='{_PANEL_HOST}', port={_PANEL_PORT}, log_level='warning')
"""
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 8
        while time.time() < deadline:
            st, _ = _http_get(f"{_PANEL_URL}health")
            if st == 200:
                break
            time.sleep(0.2)
        else:
            if proc:
                proc.terminate()
            return _fail("D8 panel server did not start on :8767")

    try:
        if live_server:
            st, html = _http_get(_PANEL_URL)
            if st != 200 or "它的设定" not in html:
                return _fail(f"D8 browser page: status={st}")
            _ok(f"D8 browser GET {_PANEL_URL} → 它的设定页面")

            rule = "手动验收 D8：用户偏好直接简短"
            st, updated = _http_json(
                "PUT",
                f"{_PANEL_URL}api/behavior/profile",
                {
                    "tone": "direct",
                    "verbosity": "short",
                    "rules": [rule],
                    "custom_notes": "D8 手动保存",
                },
            )
            if st != 200 or rule not in " ".join(updated.get("rules", [])):
                return _fail(f"D8 PUT profile: {st} {updated}")
            _ok("D8 修改行为规则并保存（HTTP API ≈ 浏览器保存）")
        else:
            from fastapi.testclient import TestClient
            from agent_platform.api.settings_panel import create_app

            client = TestClient(create_app(config=cfg, service=svc))
            page = client.get("/")
            if "它的设定" not in page.text:
                return _fail("D8 panel HTML missing title")
            rule = "手动验收 D8：用户偏好直接简短"
            updated = client.put(
                "/api/behavior/profile",
                json={"tone": "direct", "verbosity": "short", "rules": [rule]},
            ).json()
            if rule not in " ".join(updated.get("rules", [])):
                return _fail(f"D8 TestClient PUT: {updated}")
            _ok("D8 设定面板 TestClient 保存（--no-live-server 模式）")

        bootstrap_agent_platform()
        # 新会话：从磁盘 reload behavior store
        store2 = BehaviorStore(resolve_profile_path(cfg), default_profile=cfg.get("default_profile") or {})
        svc2 = BehaviorService(config=cfg, store=store2)
        import agent_platform.behavior.service as bs

        orig = bs.BehaviorService
        bs.BehaviorService = lambda **kw: svc2  # type: ignore[assignment,misc]
        try:
            pr = json.loads(agent_behavior_get_prompt({}))
        finally:
            bs.BehaviorService = orig

        prompt = pr.get("system_prompt", "")
        if rule not in prompt and "直接简短" not in prompt:
            return _fail(f"D8 get_prompt missing saved rule: {prompt[:200]}")
        _ok("D8 新会话 agent_behavior_get_prompt 反映面板变更")
        return True
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=5)


def d9_cross_session_style(*, simulate_days: int) -> bool:
    """D9 — 跨会话偏好 + 行为档（进程重启模拟；真实 ≥3 天为 D9b 可选）。"""
    from agent_platform.behavior.service import BehaviorService
    from agent_platform.behavior.store import BehaviorStore
    from agent_platform.memory.adapters.mock import MockMemAdapter
    from agent_platform.memory.service import MemoryService

    td = tempfile.mkdtemp(prefix="m7_d9_")
    root = Path(td)
    beh_cfg = {
        "enabled": True,
        "default_profile": {
            "tone": "direct",
            "verbosity": "short",
            "language": "zh-CN",
            "rules": ["回复尽量简短直接"],
        },
        "store": {"root": str(root / "behavior"), "profile_file": "profile.yaml"},
        "drift": {"enabled": True, "threshold": 0.35, "max_chars_short": 280},
    }
    mem_cfg = {
        "backend": "mock",
        "gate": {"enabled": False},
        "mock": {"persist_path": str(root / "mem.json")},
    }

    # Day 1
    store1 = BehaviorStore(root / "behavior" / "profile.yaml", default_profile=beh_cfg["default_profile"])
    beh1 = BehaviorService(config=beh_cfg, store=store1)
    beh1.apply_preference_hint("我喜欢直接简短的回应")
    mem1 = MemoryService(adapter=MockMemAdapter(persist_path=root / "mem.json"), config=mem_cfg)
    mem1.write("US3_D9：用户偏好回复尽量简短", category=__import__("agent_platform.memory.contracts", fromlist=["MemoryCategory"]).MemoryCategory.preference)

    # Day N restart
    for day in range(2, simulate_days + 1):
        store_n = BehaviorStore(root / "behavior" / "profile.yaml", default_profile=beh_cfg["default_profile"])
        beh_n = BehaviorService(config=beh_cfg, store=store_n)
        block = beh_n.system_prompt_block()
        if "简短" not in block:
            return _fail(f"D9 day{day} behavior prompt lost 简短: {block[:120]}")
        mem_n = MemoryService(adapter=MockMemAdapter(persist_path=root / "mem.json"), config=mem_cfg)
        hits = mem_n.search("简短")
        if not hits.hits:
            return _fail(f"D9 day{day} memory preference missing")

    _ok(f"D9 跨会话模拟 {simulate_days} 天重启 → 行为档 + 偏好记忆仍生效")
    if simulate_days < 3:
        _skip("D9b 真实日历 ≥3 天需作者自行记录（见 docs/M7-us-acceptance.md）")
    return True


def check_hermes_plugin_installed() -> bool:
    link = Path.home() / ".hermes" / "plugins" / "agent-calibration"
    return link.is_symlink() or link.is_dir()


def print_manual_checklist() -> None:
    print(
        """
--- 手动验收清单（D7–D9，签字用）---

D7 Hermes 真对话（可选，需插件）:
  bash agent_platform/integrations/hermes/install_plugin.sh
  hermes plugins enable agent-calibration
  hermes tools enable agent_calibration agent_behavior agent_memory

  对话剧本：
  1. 「你之前说的那个版本号是多少来着？」→ 应不确定或查工具，禁止编造
  2. 「其实你之前说的是 v0.3，错了」→ 道歉 + 更新记忆
  3. 再问版本 → 应答 v0.3

  本脚本 D7 段已用同进程工具 handler 复现上述三步。

D8 浏览器（真机）:
  PYTHONPATH=. python -m agent_platform.api.settings_panel
  打开 http://127.0.0.1:8767/ → 改规则 → 保存
  hermes 新会话：agent_behavior_get_prompt 应含新规则

D9 真实 3 天（D9b，可选）:
  首日口述偏好 → 3 天后重启 hermes → 风格仍简短
  本脚本 D9 为进程重启模拟；日历 3 天请作者自行打卡。

签字表：docs/M7-us-acceptance.md §5
"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description="M7 manual acceptance D7–D9")
    p.add_argument("--skip-d7", action="store_true")
    p.add_argument("--skip-d8", action="store_true")
    p.add_argument("--skip-d9", action="store_true")
    p.add_argument("--no-live-server", action="store_true", help="D8 use TestClient only")
    p.add_argument("--d9-days", type=int, default=3, help="simulated restart days for D9")
    p.add_argument("--checklist", action="store_true", help="print human checklist and exit")
    args = p.parse_args()

    if args.checklist:
        print_manual_checklist()
        return 0

    print("=== accept_m7_manual (D7–D9) ===\n")

    if not args.skip_d7:
        if not d7_hermes_us6_conversation(isolated_memory=True):
            print("accept_m7_manual: FAIL", file=sys.stderr)
            return 1
        if check_hermes_plugin_installed():
            _ok("D7 Hermes plugin agent-calibration symlink present")
        else:
            _skip("D7 Hermes plugin not installed (~/.hermes/plugins/agent-calibration)")

    if not args.skip_d8:
        if not d8_browser_settings_panel(live_server=not args.no_live_server):
            print("accept_m7_manual: FAIL", file=sys.stderr)
            return 1

    if not args.skip_d9:
        if not d9_cross_session_style(simulate_days=max(2, args.d9_days)):
            print("accept_m7_manual: FAIL", file=sys.stderr)
            return 1

    print("\naccept_m7_manual: PASS — D7/D8/D9 rehearsal OK")
    print_manual_checklist()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

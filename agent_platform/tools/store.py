"""Tools data directory — sandbox + drafts (M6)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_platform.tools._config import load_mcp_config, resolve_sandbox_root, resolve_store_root
from agent_platform.tools.contracts import ToolsStoreLayout

_LOG_SEED = """# Tools / MCP Event Log

Append-only log for tool invoke / draft gate (M6).

"""


def layout_for(root: Path, sandbox: Path, cfg: dict) -> ToolsStoreLayout:
    store = cfg.get("store") or {}
    drafts_name = store.get("drafts_dir", "drafts")
    log_name = store.get("events_log", "events.log.md")
    return ToolsStoreLayout(
        root=root.resolve(),
        sandbox_root=sandbox.resolve(),
        drafts_dir=root / drafts_name,
        events_log_path=root / log_name,
    )


def ensure_store(
    store_root: Path | None = None,
    sandbox_root: Path | None = None,
) -> ToolsStoreLayout:
    cfg = load_mcp_config()
    root = store_root or resolve_store_root(cfg)
    sandbox = sandbox_root or resolve_sandbox_root(cfg)
    lay = layout_for(root, sandbox, cfg)
    lay.root.mkdir(parents=True, exist_ok=True)
    lay.sandbox_root.mkdir(parents=True, exist_ok=True)
    lay.drafts_dir.mkdir(parents=True, exist_ok=True)
    if bool((cfg.get("sandbox") or {}).get("auto_init", True)):
        sample = lay.sandbox_root / "README.md"
        if not sample.is_file():
            sample.write_text(
                "# MCP sandbox\n\nLocal filesystem tool root for M6.\n",
                encoding="utf-8",
            )
    if not lay.events_log_path.is_file():
        lay.events_log_path.write_text(_LOG_SEED, encoding="utf-8")
    return lay


def append_event_log(lay: ToolsStoreLayout, line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with lay.events_log_path.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} {line}\n")

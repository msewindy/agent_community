"""M6 — ToolService invoke + draft gate."""

from __future__ import annotations

from pathlib import Path

from agent_platform.tools.contracts import (
    DraftApproveRequest,
    ToolInvokeRequest,
    ToolInvokeStatus,
)
from agent_platform.tools.service import ToolService


def _svc(tmp_path: Path) -> ToolService:
    root = tmp_path / "store"
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "a.txt").write_text("hi", encoding="utf-8")
    cfg = {
        "enabled": True,
        "sandbox": {"root": str(sandbox), "auto_init": False},
        "governance": {
            "tool_levels": {
                "filesystem.read_file": "L0",
                "filesystem.write_file": "L2",
            }
        },
        "draft_gate": {"enabled": True},
        "store": {"root": str(root)},
    }
    return ToolService(config=cfg, store_root=root, sandbox_root=sandbox)


def test_l0_read(tmp_path: Path):
    svc = _svc(tmp_path)
    r = svc.invoke(
        ToolInvokeRequest(
            server="filesystem",
            tool="read_file",
            arguments={"path": "a.txt"},
            session_id="t",
        )
    )
    assert r.status == ToolInvokeStatus.executed
    assert r.output["content"] == "hi"


def test_l2_draft_flow(tmp_path: Path):
    svc = _svc(tmp_path)
    sandbox = svc.sandbox_root
    pending = svc.invoke(
        ToolInvokeRequest(
            server="filesystem",
            tool="write_file",
            arguments={"path": "b.txt", "content": "x"},
            session_id="t",
        )
    )
    assert pending.status == ToolInvokeStatus.draft_pending
    assert not (sandbox / "b.txt").is_file()

    done = svc.approve_draft(DraftApproveRequest(draft_id=pending.draft_id, session_id="t"))
    assert done.status == ToolInvokeStatus.executed
    assert (sandbox / "b.txt").read_text(encoding="utf-8") == "x"

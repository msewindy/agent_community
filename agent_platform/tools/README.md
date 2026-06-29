# 工具层（M6 / C2 + C3）

MCP 工具门面 + **L0–L2 分级治理** + **L2 草稿确认门控**。

| 级别 | 行为 |
|------|------|
| L0 | 只读（读文件、fetch、搜索）— 直接执行 |
| L1 | 低风险写 — 直接执行 |
| L2 | 破坏性/外发 — 先 `draft_pending`，用户 `approve` 后执行 |

```bash
PYTHONPATH=. python agent_platform/tools/smoke_tools_d1.py
PYTHONPATH=. python agent_platform/tools/smoke_tools_d2.py
PYTHONPATH=. python agent_platform/tools/smoke_tools_d3.py   # 真 MCP stdio（需 npx）
PYTHONPATH=. python agent_platform/tools/smoke_draft_panel.py
PYTHONPATH=. python -m agent_platform.api.draft_panel      # http://127.0.0.1:8766/
PYTHONPATH=. python agent_platform/tools/accept_m6_smoke.py
PYTHONPATH=. python agent_platform/tools/accept_m6_us.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_tools_mcp.py
PYTHONPATH=. python agent_platform/tools/cli_tools.py status
```

详见 [docs/M6-mcp-tools.md](../../docs/M6-mcp-tools.md)。

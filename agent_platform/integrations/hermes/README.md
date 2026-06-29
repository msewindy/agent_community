# Hermes 集成（M2 D8 + M3 D7）

## 记忆（M2）— `agent-memverse`

与内置 `memory`（MEMORY.md）**分工**：

| 工具 | 用途 |
|------|------|
| `memory` | Hermes 有界 curated 笔记 |
| `agent_memory_write` | 用户事实/偏好 → MemVerse |
| `agent_memory_search` | 跨会话召回 |
| `agent_memory_delete` | US-7 tombstone |

## Wiki（M3）— `agent-wiki`

| 工具 | 用途 |
|------|------|
| `wiki_ingest` | raw/ → wiki 编译页 + index + log |
| `wiki_query` | 检索 wiki + 摘录 answer |
| `wiki_precipitate_evaluate` | 是否提示沉淀（D6） |
| `agent_combined_recall` | M2 记忆 + M3 Wiki 一次召回（D9） |

**禁止**：用户偏好写 wiki；主题知识写 MemVerse。

## MCP 工具（M6）— `agent-tools`

| 工具 | 用途 |
|------|------|
| `agent_tool_status` | 沙箱路径、已注册工具、待确认草稿数 |
| `agent_tool_invoke` | 经 L0–L2 治理调用 MCP（L2 → `draft_pending`） |
| `agent_tool_list_drafts` | 列出待确认 L2 草稿 |
| `agent_tool_approve_draft` | 用户确认后执行 L2 操作 |
| `agent_tool_reject_draft` | 拒绝草稿 |

**流程**：`agent_tool_invoke`（write/delete）→ 向用户展示 `preview` → 用户确认 → `agent_tool_approve_draft` 或打开草稿面板 `http://127.0.0.1:8766/`。

## 主动行为（M5）— `agent-proactive`

| 工具 | 用途 |
|------|------|
| `agent_proactive_evaluate` | 主动发声前检查（静默时段 / snooze / 工时） |
| `agent_proactive_feedback` | 「别打扰」→ 会话静默 + 写记忆（dedup） |
| `agent_proactive_report_work` | 上报连续工作分钟数 |
| `agent_proactive_status` | 策略与会话状态 |

## 安装

```bash
chmod +x agent_platform/integrations/hermes/install_plugin.sh
./agent_platform/integrations/hermes/install_plugin.sh
```

```bash
hermes plugins enable agent-memverse
hermes plugins enable agent-wiki
hermes tools enable agent_memory
hermes tools enable agent_wiki
hermes tools enable agent_recall
hermes plugins enable agent-proactive
hermes tools enable agent_proactive
hermes plugins enable agent-tools
hermes tools enable agent_tools
```

## 冒烟（无需 Hermes CLI）

```bash
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_tools.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_wiki_tools.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_proactive_tools.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_tools_mcp.py
PYTHONPATH=. python agent_platform/integrations/demo_recall_m2_m3.py
PYTHONPATH=. python agent_platform/wiki/accept_m3_d9.py
```

## 配置

| 层 | 配置 |
|----|------|
| 记忆 | `agent_platform/config/memory.yaml` |
| Wiki | `agent_platform/config/wiki.yaml` |

环境变量：`AGENT_COMMUNITY_ROOT`（各插件目录内 `AGENT_COMMUNITY_ROOT` 文件）

`current_session_id` → `trace_id` 前缀 `hermes-`

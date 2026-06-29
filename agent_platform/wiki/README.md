# Wiki 层（M3）

| 里程碑 | 状态 |
|--------|------|
| D1 配置 + 契约 + 目录种子 | ✅ |
| D2 `wiki_service.ingest`（单 raw → 1 页） | ✅ |
| D3 index/log 更新 | ✅ |
| D4 query（index + ripgrep/qmd） | ✅ |
| D5 CLI smoke + pytest | ✅ |
| D6 沉淀触发 precipitate | ✅ |
| D7 Hermes wiki_* 工具 | ✅ |
| D8 US-4 验收 accept_m3_us4 | ✅ |
| D9 M2+M3 联合召回 | ✅ |
| D10 M3 文档签字 | ✅ |

## 快速开始

```bash
cd /home/lfw/project/agent_community
pip install -r agent_platform/requirements-memory.txt

PYTHONPATH=. python agent_platform/wiki/smoke_wiki.py --isolated
PYTHONPATH=. python agent_platform/wiki/accept_m3_smoke.py
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py smoke
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d1.py
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py init
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py validate
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d2.py
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d3.py
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d4.py
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py query "your topic"
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d6.py
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py precipitate-simulate
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py ingest raw/articles/note.md --topic "My Topic"
PYTHONPATH=. python agent_platform/wiki/export_schema.py

# M3 D8 US-4 验收
PYTHONPATH=. python agent_platform/wiki/accept_m3_us4.py
PYTHONPATH=. python agent_platform/integrations/demo_recall_m2_m3.py
PYTHONPATH=. python agent_platform/wiki/accept_m3_d9.py
```

详见 [docs/M3-us-acceptance.md](../../docs/M3-us-acceptance.md)、[docs/M3-baseline.md](../../docs/M3-baseline.md)。

默认数据目录：`wiki_data/`（见 `agent_platform/config/wiki.yaml`）。

## 文档

- [docs/M3-llm-wiki.md](../../docs/M3-llm-wiki.md)
- [docs/M2-M3-interface.md](../../docs/M2-M3-interface.md)

## 模块

| 文件 | 说明 |
|------|------|
| `contracts.py` | WikiPort、请求/响应模型、JSON Schema 导出 |
| `store.py` | 目录骨架 `ensure_store` / `validate_store` |
| `catalog.py` | `index.md` / `log.md` 维护 |
| `ingest.py` | 单文件编译为 wiki 页 |
| `query.py` | index + ripgrep/qmd 检索与 answer 拼装 |
| `precipitate.py` | 何时提示沉淀（D6） |
| `service.py` | `WikiService` 门面 |
| `_config.py` | 加载 `wiki.yaml` |

# MemVerse 本地部署（M2）

## amd64（本机已验证）

1. 修正上游 `MemoryKB/User_Conversation/_init_.py` → `__init__.py`（否则 `ModuleNotFoundError`）。
2. 构建镜像：`cd research_repos/MemVerse && docker build -t memverse-local:amd64 .`
3. 启动：`source agent_platform/deploy/memverse/env.sh && docker compose -f agent_platform/deploy/memverse/docker-compose.yml up -d`

## 环境变量（D4）

| 变量 | 默认 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 来自 `~/.hermes/.env` | DeepSeek Key |
| `OPENAI_API_BASE` | `https://api.deepseek.com/v1` | OpenAI 兼容 |
| `OPENAI_MODEL` | `deepseek-chat` | 与 Hermes M0 一致 |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | LightRAG 嵌入 |

修改模型后需 **重建镜像** 并 `docker compose up -d --force-recreate`。

## 端口

| 服务 | 端口 |
|------|------|
| FastAPI | 8000 |
| MCP | 5250 |

## 官方 arm64 镜像

`docker pull yifeisunecust/memverse:v1.1.0` 在 linux/amd64 上无 manifest；Apple Silicon / arm64 可直接用官方镜像。

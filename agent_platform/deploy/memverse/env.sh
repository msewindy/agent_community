#!/usr/bin/env bash
# 从 Hermes 环境加载 DeepSeek（OpenAI 兼容）供 MemVerse 使用。
set -euo pipefail

HERMES_ENV="${HOME}/.hermes/.env"
if [[ -f "${HERMES_ENV}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${HERMES_ENV}"
  set +a
fi

if [[ -z "${DEEPSEEK_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
  echo "错误: 未找到 DEEPSEEK_API_KEY（请配置 ~/.hermes/.env）" >&2
  exit 1
fi

export OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEPSEEK_API_KEY}}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://api.deepseek.com/v1}"
# 与 Hermes M0 对齐；若网关仅支持 v4 系列可改为 deepseek-v4-flash
export OPENAI_MODEL="${OPENAI_MODEL:-deepseek-chat}"
export OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}"

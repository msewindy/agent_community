# agent_community

基于 Hermes + MemVerse 的个人 Agent：**记忆（M2）+ 自我进化（C7）** 主线。

## 本机快速验收（WSL2 Ubuntu）

**所有部署、运行、测试均在 WSL2 内进行**（Hermes 安装在 `~/.hermes`）。

```bash
cd /mnt/c/Users/Administrator/Desktop/agent_community

# 环境检查
bash scripts/check_wsl_env.sh

# 挂载 agent 插件 + 启用
bash scripts/install_hermes_plugins_wsl.sh
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
hermes plugins enable agent-memverse
hermes plugins enable agent-evolution

# MemVerse Docker + 全量验收（M2 + C7 Phase 1–4）
bash scripts/run_memverse_wsl.sh          # 启动容器 :8000
bash scripts/run_wsl_acceptance.sh --memverse
python agent_platform/evolution/accept_c7_phase4.py

# 文本交互全功能自动化（M2–M8 除 US-2 + C7 + Hermes smoke）
bash scripts/run_wsl_text_full_acceptance.sh
# M2 跨会话落盘预检
bash scripts/verify_m2_memory_persist.sh
# 详见 docs/功能测试验证方案.md
```

## 文档

| 文档 | 说明 |
|------|------|
| [docs/项目架构与配置说明.md](docs/项目架构与配置说明.md) | **架构、功能、配置、部署** |
| [docs/功能测试验证方案.md](docs/功能测试验证方案.md) | **全功能测试验证（自动化 + Hermes + 面板）** |
| [docs/模型与产品层边界.md](docs/模型与产品层边界.md) | **模型 / Hermes / 产品层边界** |
| [项目整理文档.md](项目整理文档.md) | 仓库整理方案 |

```bash
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
hermes chat
```

## 仓库收拢

非核心参考库/数据可迁入 `temp/`：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reorganize_to_temp.ps1
```

## 保留的 research_repos

- `MemVerse` — M2 记忆后端（Docker 构建）
- `hermes-agent` — 运行时参考
- `leaper-agent`, `reflexion`, `MemOS` — C7 进化参考

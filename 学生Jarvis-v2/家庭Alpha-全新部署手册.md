# 家庭 Alpha · 全新部署手册（WSL2 / Mac mini）

> **版本**：学生 Jarvis v2 · 家庭 Alpha · 封版部署（2026-Q3）  
> **适用场景**：**新机或清数据后**从零安装，不依赖旧机 `student_data`  
> **配套文档**：[家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md)（日常启停）· [家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md)（验收打勾）

---

## 0. 这份手册解决什么

| 文档 | 用途 |
|------|------|
| **本手册** | 新机安装：系统依赖 → 代码 → Hermes → 插件 → 学生初始化 → 双服务 → 验收 |
| 启动手册 | 已部署环境下的每日启停与话术 |
| 手动验证手册 | 封版前/上线前逐项功能验收 |

---

## 1. 架构一览（部署时要跑什么）

```
┌─────────────────────────────────────────────────────────────┐
│  家庭服务器（WSL2 / Mac mini / Linux）                       │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐                      │
│  │ 8771 孩子端   │     │ 8770 家长端   │                      │
│  │ student_chat │     │ student_panel│                      │
│  └──────┬───────┘     └──────┬───────┘                      │
│         │                    │                              │
│         └────────┬───────────┘                              │
│                  ▼                                          │
│         agent_platform/（本仓库 Python 代码）                │
│                  │                                          │
│         ┌────────┴────────┐                                 │
│         ▼                 ▼                                 │
│   ~/.hermes/         本地数据目录（git 外）                   │
│   Hermes + 插件       student_data/ wiki_data/ questions.db │
│   + API Keys                                                │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ 云端 API（需密钥）
   DeepSeek（对话/推题/归类）
   阿里云 DashScope（拍照 Vision，可选但推荐）
```

**两个必开服务**

| 端口 | 进程 | 用户 |
|------|------|------|
| **8771** | `agent_platform.api.student_chat` | 孩子（聊天、练题、拍照） |
| **8770** | `agent_platform.api.student_panel` | 家长（学情、知识点入库、习题处理） |

**不需要单独部署数据库**：题库为 SQLite（`questions.db`），学情为 `student_data/` 下 JSON 文件。

---

## 2. 部署模式选择

### 2.1 模式 A — 全新部署（推荐封版默认）

- 只拉代码 + 配置，**不复制**旧机 `student_data/`
- 自动导入种子题库、种子知识点库（`kp_catalog.json`）
- 通过 CLI 初始化学生 `g2-stu-01`
- 适合：Mac mini 作为正式家庭服务器，历史学情从零开始

### 2.2 模式 B — 迁移部署（保留历史学情）

在模式 A 完成后，从旧机器复制（**先停双服务**）：

| 路径 | 说明 |
|------|------|
| `student_data/` | 学情、做题记录、gap、收件箱等（**整目录**） |
| `wiki_data/` | 若曾自定义 Wiki 讲解页 |
| `agent_platform/learning/catalog/kp_catalog.json` | 若旧机批准入库后 catalog 有增量 |
| `agent_platform/learning/question_bank/questions.db` | 若旧机有额外导入题 |

复制后重启 8770 / 8771；家长端可调 `POST /api/kp/catalog/reload` 刷新 catalog 缓存。

### 2.3 模式 C — WSL2 本机重置（已装 Hermes、仅清数据）

适用于 Windows 开发机 WSL：保留 Hermes 与 API Key，清空学情/M2/Wiki/题库运行时数据后单用户重建。

```bash
export AGENT_COMMUNITY_ROOT=/mnt/c/Users/你的用户名/Desktop/agent_community
bash "$AGENT_COMMUNITY_ROOT/scripts/wsl_family_alpha_reset.sh" all
```

完成后按 [家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md) 启动 8770/8771。

---

## 3. 硬件与网络

| 项 | 建议 |
|----|------|
| 机器 | Mac mini（Apple Silicon 或 Intel 均可） |
| 内存 | ≥ 8 GB（Hermes + 本地模型依赖建议 16 GB） |
| 磁盘 | ≥ 20 GB 可用（含 Hermes venv、题库、日志） |
| 网络 | 家庭 WiFi；Mac 与孩子平板/手机 **同一局域网** |
| 浏览器 | Chrome / Safari / Edge |
| 防火墙 | 允许局域网访问 **8770、8771**（孩子平板用 Mac 的局域网 IP，不能用 `127.0.0.1`） |

查看 Mac 局域网 IP：

```bash
ipconfig getifaddr en0    # Wi-Fi 常见
# 或：系统设置 → 网络 → Wi-Fi → 详细信息 → IP 地址
```

孩子端地址：`http://<Mac局域网IP>:8771/`  
家长端地址：`http://127.0.0.1:8770/`（仅家长本机）或 `http://<Mac局域网IP>:8770/`

---

## 4. 系统前置依赖（Mac）

在 **终端.app** 或 iTerm 中执行。

### 4.1 安装 Homebrew（若未安装）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

按安装完成提示把 `brew` 加入 `PATH`（Apple Silicon 常见为 `/opt/homebrew/bin`）。

### 4.2 基础工具

```bash
brew install git python@3.11
```

确认版本：

```bash
python3 --version    # 建议 3.11+
git --version
```

### 4.3 安装 Hermes Agent

Hermes 是本项目的 Agent 运行时（对话、工具调用）。按官方方式安装到 `~/.hermes`（与 Windows/WSL 开发机相同布局）。

> 若你已在其他机器装过 Hermes，可在 Mac 上 **重新执行官方安装脚本**，或从旧机打包复制 `~/.hermes/hermes-agent/` 与 `~/.hermes/.env`（注意密钥安全）。

安装后确认：

```bash
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$HOME/.local/bin:$PATH"
hermes --version
```

### 4.4 API 密钥（必做）

创建或编辑 `~/.hermes/.env`：

```bash
mkdir -p ~/.hermes
chmod 700 ~/.hermes
nano ~/.hermes/.env
```

至少包含：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxx
# 拍照 / Vision 理解（模块 E 验收需要）
DASHSCOPE_API_KEY=sk-xxxxxxxx
```

可选：

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

---

## 5. 获取项目代码

建议目录（可自定，下文用 `$REPO`）：

```bash
export REPO="$HOME/agent_community"
git clone <你的仓库地址> "$REPO"
cd "$REPO"
```

封版部署请检出 **已封版 tag/分支**（与验证报告一致）。

### 5.1 持久化环境变量

写入 `~/.zshrc`（bash 用户写 `~/.bashrc`）：

```bash
export AGENT_COMMUNITY_ROOT="$HOME/agent_community"
export PYTHONPATH="$AGENT_COMMUNITY_ROOT"
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$HOME/.local/bin:$PATH"
export PY="$HOME/.hermes/hermes-agent/venv/bin/python"
```

生效：

```bash
source ~/.zshrc
cd "$AGENT_COMMUNITY_ROOT"
```

---

## 6. Python 依赖（Hermes venv 内）

**统一使用 Hermes 自带 venv**，避免与系统 Python 混用：

```bash
cd "$AGENT_COMMUNITY_ROOT"
$PY -m pip install -U pip

$PY -m pip install -r agent_platform/requirements-memory.txt
$PY -m pip install -r agent_platform/requirements-wiki.txt
$PY -m pip install -r agent_platform/requirements-tools.txt
$PY -m pip install -r agent_platform/requirements-perception.txt

# 孩子端 TTS（浏览器点朗读时需要）
$PY -m pip install edge-tts
```

验证 import：

```bash
$PY -c "import agent_platform; import fastapi; import uvicorn; print('ok')"
```

---

## 7. 安装并启用 Hermes 插件

### 7.1 安装插件软链接

在 Mac 上直接运行仓库脚本（与 WSL 脚本等价，推荐用完整安装脚本）：

```bash
cd "$AGENT_COMMUNITY_ROOT"
bash agent_platform/integrations/hermes/install_plugin.sh
```

确认 `~/.hermes/plugins/` 下存在 `agent-student`、`agent-wiki` 等，且各插件目录内有 `AGENT_COMMUNITY_ROOT` 文件指向本仓库。

### 7.2 启用插件与工具

```bash
hermes plugins enable agent-memverse agent-evolution agent-wiki \
  agent-proactive agent-tools agent-calibration agent-perception agent-student

hermes tools enable agent_memory agent_evolution agent_wiki agent_perception \
  agent_proactive agent_tools agent_calibration agent_behavior agent_student
```

### 7.3 健康检查

```bash
hermes doctor
```

**必须通过**：`✓ agent_student`（及对话所需的 memory/wiki 等工具集）。

未通过时检查：`PATH`、`AGENT_COMMUNITY_ROOT`、`PYTHONPATH`、插件软链接是否断裂。

---

## 8. 项目配置检查（一般无需改）

主配置：`agent_platform/config/student_learning.yaml`

封版默认要点：

| 键 | 默认值 | 说明 |
|----|--------|------|
| `hermes.default_student_id` | `g2-stu-01` | 孩子端默认学生 |
| `students.profiles.*.preferred_name` | （不配置） | 显示名由 **M2 user_profile / onboarding** 写入，勿在 yaml 写死 |
| `default_curriculum.unit_id` | `math-g3-mixed-ops` | 当前主攻单元 |
| `pilot.grade_level` | `3` | 三年级 |
| `data.root` | `student_data` | 学情数据目录（相对仓库根） |
| `kp_catalog.path` | `agent_platform/learning/catalog/kp_catalog.json` | 知识点库 |
| `question_bank.sqlite_path` | `agent_platform/learning/question_bank/questions.db` | 题库 |

**三科支持（数学 / 语文 / 英语）**：catalog 含 `english-g3-starter`；英语错因见 `error_taxonomy`；完整录入样例 `docs/content/英语-三年级.kp.md`；手动验收见 [家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md) **模块 H**。

**修改此文件后需重启 8771（孩子端）**；8770 建议一并重启。

---

## 9. 学生与数据初始化（全新部署关键步骤）

> `student_data/` **不在 git 中**。新机必须执行本节，否则家长端学生列表为空、孩子端无法注入学情。

### 9.1 创建学生上下文

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.

$PY -m agent_platform.learning.cli_student init g2-stu-01 --from-defaults
```

预期：在 `student_data/g2-stu-01/context.json` 生成文件，当前单元为 `math-g3-mixed-ops`。

### 9.2 入学档案（可选，建议执行）

```bash
$PY -m agent_platform.learning.cli_student onboard g2-stu-01 \
  --grade 三年级 --grade-level 3 --subject 数学
```

### 9.3 预建推题队列

```bash
$PY -m agent_platform.learning.cli_student push rebuild g2-stu-01
```

### 9.4 验证 CLI

```bash
$PY -m agent_platform.learning.cli_student show g2-stu-01
$PY -m agent_platform.learning.cli_student push peek g2-stu-01
```

### 9.5 启动时自动引导（无需手工）

首次启动 8770 / 8771 时会调用 `ensure_family_alpha_content()`，自动完成：

- 种子题导入 SQLite（若题库为空）
- 校验种子包（taxonomy / 题量）
- 为试点单元补建 Wiki 讲解页（`wiki_data/`，`kp_wiki.bootstrap_pilot_units: true`）

查看引导结果：访问 `http://127.0.0.1:8770/health` 或 `http://127.0.0.1:8771/health` 中的 `bootstrap` 字段。

---

## 10. 启动服务

开 **两个终端窗口**（或使用 §11 的 launchd 后台）。

### 终端 A — 孩子端 8771

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.
$PY -m uvicorn agent_platform.api.student_chat:app --host 0.0.0.0 --port 8771
```

### 终端 B — 家长端 8770

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.
$PY -m uvicorn agent_platform.api.student_panel:app --host 0.0.0.0 --port 8770
```

### 访问地址

| 角色 | URL |
|------|-----|
| 孩子（Mac 本机） | http://127.0.0.1:8771/ |
| 孩子（平板/手机） | http://\<Mac局域网IP\>:8771/ |
| 家长学情 | http://127.0.0.1:8770/ |
| 浏览知识库 | http://127.0.0.1:8770/kp-catalog |
| 知识点入库 | http://127.0.0.1:8770/kp-review |
| 习题处理 | http://127.0.0.1:8770/exercises |

---

## 11. 部署验收（建议顺序）

### 11.1 自动化测试（部署后先跑）

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.

$PY -m pytest \
  agent_platform/tests/test_bootstrap_family_alpha.py \
  agent_platform/tests/test_student_panel_learning_unit.py \
  agent_platform/tests/test_student_panel_kp_review.py \
  agent_platform/tests/test_student_panel_question_bank.py \
  agent_platform/tests/test_student_hermes_tools.py \
  -q
```

退出码应为 `0`。

完整封版验收请按 [家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md) 全量 pytest + 手动模块 A–G。

### 11.2 最小冒烟（5 分钟）

| # | 检查 | 预期 |
|---|------|------|
| 1 | `curl -s http://127.0.0.1:8770/health` | `"status":"ok"`，`bootstrap.ok` 为 true |
| 2 | `curl -s http://127.0.0.1:8771/health` | 同上 |
| 3 | 浏览器打开 8770 | 学情总览有 `g2-stu-01`；显示名初始可为 student_id，对话后由 M2 更新 |
| 4 | 浏览器打开 8771 | 能发送消息并收到回复（约 10–30s） |
| 5 | 8771 说「再给我 3 道题」 | 返回 G3 混合运算相关题 |

### 11.3 封版手动验收

按 [家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md) 逐项打勾，重点：

- **模块 C**：知识点/题/Wiki 入库  
- **模块 E**：孩子对话 + 拍照闭环  
- **模块 G**：批准后 **不重启 8771**，新 KP 可讲解（catalog 热加载）

---

## 12. 可选：Mac 开机自启（launchd）

适合 Mac mini 长期当家庭服务器。示例 plist 路径 `~/Library/LaunchAgents/com.family.jarvis.student-chat.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.family.jarvis.student-chat</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/你的用户名/.hermes/hermes-agent/venv/bin/python</string>
    <string>-m</string><string>uvicorn</string>
    <string>agent_platform.api.student_chat:app</string>
    <string>--host</string><string>0.0.0.0</string>
    <string>--port</string><string>8771</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/你的用户名/agent_community</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key><string>/Users/你的用户名/agent_community</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/jarvis-8771.log</string>
  <key>StandardErrorPath</key><string>/tmp/jarvis-8771.err</string>
</dict>
</plist>
```

复制一份改端口为 8770、`student_panel`、日志路径，作为家长端。

加载：

```bash
launchctl load ~/Library/LaunchAgents/com.family.jarvis.student-chat.plist
launchctl load ~/Library/LaunchAgents/com.family.jarvis.student-panel.plist
```

卸载：`launchctl unload ...`

---

## 13. 目录与备份建议

| 路径 | 是否入 git | 备份建议 |
|------|-----------|----------|
| `student_data/` | 否 | **每周备份**（学情核心） |
| `agent_platform/learning/catalog/kp_catalog.json` | 是（种子）/ 批准后可能本地变更 | 批准入库后纳入备份 |
| `agent_platform/learning/question_bank/questions.db` | 部分 | 有自定义题后备份 |
| `wiki_data/` | 否 | 有自定义讲解后备份 |
| `~/.hermes/.env` | 否 | 密钥单独安全保管，勿提交 git |

---

## 14. 常见问题

| 现象 | 处理 |
|------|------|
| 家长端学生列表为空 | 未执行 §9.1 `cli_student init` |
| `hermes doctor` 无 `agent_student` | 重做 §7 插件安装与 enable |
| 8771 回复「尚未初始化 StudentContext」 | §9.1 初始化学生；确认 `default_student_id` 一致 |
| 平板打不开 8771 | 用 Mac **局域网 IP**；检查防火墙 |
| 拍照无反应 | 确认 `DASHSCOPE_API_KEY`；浏览器需允许相机 |
| 批准新 KP 后孩子仍不认识 | 一般无需重启 8771；再问一题触发工具调用；仍失败见模块 G3 |
| 改了 `student_learning.yaml` 不生效 | 重启 **8771**（改配置必须重启） |
| 改了 HTML/模板不生效 | 重启对应 uvicorn 进程（模板启动时读入内存） |
| `ImportError: agent_platform` | 确认 `cd` 到仓库根且 `export PYTHONPATH=.` |

---

## 15. 部署完成后的日常运维

日常启停、话术、每周家长 checklist → [家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md)

**记住三句话**：

1. 双服务常开：8771（孩子）+ 8770（家长）  
2. 改配置重启 8771；批准新知识点一般 **不用** 重启  
3. 定期备份 `student_data/`

---

**部署清单（可打印打勾）**

- [ ] Homebrew + Python 3.11+  
- [ ] Hermes 安装，`hermes --version` 正常  
- [ ] `~/.hermes/.env` 含 DEEPSEEK + DASHSCOPE  
- [ ] 代码 clone，`AGENT_COMMUNITY_ROOT` / `PYTHONPATH` 已写入 shell  
- [ ] pip 依赖安装完成  
- [ ] `install_plugin.sh` + `hermes doctor` → `✓ agent_student`  
- [ ] `cli_student init g2-stu-01 --from-defaults`  
- [ ] `cli_student push rebuild g2-stu-01`  
- [ ] （WSL 可选）`wsl_family_alpha_reset.sh all` 已跑通  
- [ ] 8771 + 8770 启动，health 正常  
- [ ] 手动验证手册模块 0 + 冒烟通过  
- [ ] （可选）launchd 自启 + `student_data` 备份策略  

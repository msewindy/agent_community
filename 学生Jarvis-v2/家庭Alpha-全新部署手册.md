# 家庭 Alpha · 全新部署手册

> **版本**：学生 Jarvis v2 · 家庭 Alpha · 三年级学习版（2026-Q3）  
> **适用场景**：**新机或清数据后**从零安装，不依赖旧机 `student_data`  
> **运行环境**：WSL2（Windows 开发/家庭服务器）或 Mac mini / Linux  
> **配套文档**：[家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md)（日常启停）· [家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md)（验收打勾）

---

## 0. 这份手册解决什么

| 文档 | 用途 |
|------|------|
| **本手册** | 从零部署：系统依赖 → Hermes → API Key → 插件 → 学生初始化 → 画像预热 → 知识点 → 双服务 → 验收 |
| 启动手册 | 已部署环境下的每日启停与话术 |
| 手动验证手册 | 封版前/上线前逐项功能验收 |

**新用户按本文顺序做完 §4–§13，即可让孩子打开 8771 聊天、家长打开 8770 管理学情。**

---

## 1. 架构一览

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
│   ~/.hermes/         本地数据（git 外）                       │
│   Hermes + 插件       student_data/ wiki_data/ questions.db │
│   + API Keys                                                │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ 云端 API（需密钥，见 §6）
   DeepSeek deepseek-chat     — 对话 / 推题 / 作业归类
   阿里云 DashScope           — 拍照理解 qwen3-vl-plus
                              — 语音识别 paraformer-realtime-v2
   edge-tts（微软，无需 Key）  — 朗读
```

**两个必开服务**

| 端口 | 进程 | 用户 |
|------|------|------|
| **8771** | `agent_platform.api.student_chat` | 孩子（聊天、练题、拍照、按住说话） |
| **8770** | `agent_platform.api.student_panel` | 家长（学情、知识点入库、习题处理） |

**不需要单独部署数据库**：题库为 SQLite（`questions.db`），学情为 `student_data/` 下 JSON 文件。

---

## 2. 部署模式选择

### 2.1 模式 A — 全新部署（推荐）

- 只拉代码 + 配置，**不复制**旧机 `student_data/`
- 自动导入种子题库、种子知识点库（`kp_catalog.json`，约 **30 单元 / 145 知识点**）
- 通过 CLI 初始化学生 `g2-stu-01`（沿用 id，当前主攻三年级）
- 适合：家庭服务器首次上线，历史学情从零开始

### 2.2 模式 B — 迁移部署（保留历史学情）

在模式 A 完成后，从旧机器复制（**先停双服务**）：

| 路径 | 说明 |
|------|------|
| `student_data/` | 学情、做题记录、gap、收件箱等（**整目录**） |
| `wiki_data/` | 自定义 Wiki 讲解页 |
| `agent_platform/learning/catalog/kp_catalog.json` | 若旧机批准入库后 catalog 有增量 |
| `agent_platform/learning/question_bank/questions.db` | 若旧机有额外导入题 |

复制后重启 8770 / 8771；家长端可调 `POST /api/kp/catalog/reload` 刷新 catalog 缓存。

### 2.3 模式 C — WSL 本机重置（已装 Hermes、仅清数据）

适用于 Windows 开发机 WSL：保留 Hermes 与 API Key，清空学情/M2/Wiki/题库运行时数据后单用户重建。

```bash
export AGENT_COMMUNITY_ROOT=/mnt/c/Users/你的用户名/Desktop/agent_community
bash "$AGENT_COMMUNITY_ROOT/scripts/wsl_family_alpha_reset.sh" all
```

脚本会自动：备份 → 清数据 → 重装插件 → `cli_student init/onboard` → bootstrap 自检。

完成后按 [家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md) 或 §10 启动 8770/8771。

---

## 3. 硬件与网络

| 项 | 建议 |
|----|------|
| 机器 | WSL2 Ubuntu 22.04+，或 Mac mini（Apple Silicon / Intel） |
| 内存 | ≥ 8 GB（建议 16 GB） |
| 磁盘 | ≥ 20 GB 可用（含 Hermes venv、题库、日志） |
| 网络 | 家庭 WiFi；电脑与孩子平板/手机 **同一局域网** |
| 浏览器 | Chrome / Edge / Safari（语音需 **localhost 或 HTTPS**） |
| 防火墙 | 允许局域网访问 **8770、8771** |

查看局域网 IP：

```bash
# WSL / Linux
hostname -I | awk '{print $1}'

# Mac Wi-Fi
ipconfig getifaddr en0
```

孩子端地址：`http://<局域网IP>:8771/`（本机可用 `http://127.0.0.1:8771/`）  
家长端地址：`http://127.0.0.1:8770/` 或 `http://<局域网IP>:8770/`

---

## 4. 系统前置依赖

### 4.1 WSL2（Windows 推荐路径）

在 **WSL Ubuntu** 终端执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ffmpeg curl
ffmpeg -version   # 语音识别 ASR 必需
```

安装 Hermes（若未安装）：

```powershell
# 在 Windows PowerShell（管理员）中，仓库根目录：
.\scripts\install_hermes_windows.ps1
```

或在 WSL 中按 [Hermes 官方文档](https://github.com/NousResearch/hermes-agent) 安装到 `~/.hermes`。

WSL 环境变量（写入 `~/.bashrc`）：

```bash
export AGENT_COMMUNITY_ROOT="/mnt/c/Users/你的用户名/Desktop/agent_community"
export PYTHONPATH="${AGENT_COMMUNITY_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export HERMES_HOME="${HOME}/.hermes"
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:${PATH}"
export PY="${HOME}/.hermes/hermes-agent/venv/bin/python"
```

```bash
source ~/.bashrc
bash "$AGENT_COMMUNITY_ROOT/scripts/check_wsl_env.sh"   # 可选：环境自检
```

### 4.2 Mac / Linux

```bash
# Mac
brew install git python@3.11 ffmpeg

# Debian/Ubuntu
sudo apt install -y git python3 ffmpeg
```

确认版本：

```bash
python3 --version    # 建议 3.11+
ffmpeg -version
git --version
```

安装 Hermes 到 `~/.hermes`（与 WSL 相同布局），并确认：

```bash
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$HOME/.local/bin:$PATH"
hermes --version
```

---

## 5. 获取项目代码

```bash
export REPO="${AGENT_COMMUNITY_ROOT:-$HOME/agent_community}"
git clone <你的仓库地址> "$REPO"
cd "$REPO"
```

持久化环境变量（WSL 写 `~/.bashrc`，Mac 写 `~/.zshrc`）：

```bash
export AGENT_COMMUNITY_ROOT="$REPO"
export PYTHONPATH="$AGENT_COMMUNITY_ROOT"
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$HOME/.local/bin:$PATH"
export PY="$HOME/.hermes/hermes-agent/venv/bin/python"
```

```bash
source ~/.bashrc   # 或 source ~/.zshrc
cd "$AGENT_COMMUNITY_ROOT"
```

---

## 6. API 密钥配置（必做）

创建或编辑 `~/.hermes/.env`：

```bash
mkdir -p ~/.hermes
chmod 700 ~/.hermes
nano ~/.hermes/.env
```

### 6.1 必填项

```env
# 对话 / 推题 / 拍作业归类（DeepSeek）
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 拍照理解 + 语音识别（阿里云百炼 DashScope，同一个 Key）
DASHSCOPE_API_KEY=sk-xxxxxxxx
```

### 6.2 各能力对应关系

| 能力 | 提供商 | 环境变量 | 模型 |
|------|--------|----------|------|
| 孩子聊天 / 学情工具 | DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat`（`voice.yaml`） |
| 拍照理解 | 阿里云百炼 | `DASHSCOPE_API_KEY` | `qwen3-vl-plus`（`perception.yaml`） |
| 按住说话识别 | 阿里云百炼 | `DASHSCOPE_API_KEY` | `paraformer-realtime-v2` |
| 朗读 TTS | edge-tts | 无需 Key | `zh-CN-XiaoxiaoNeural` |

> **注意**：`DASHSCOPE_API_KEY` 与 `DEEPSEEK_API_KEY` 是两套密钥；语音和图像共用 DashScope Key，但不是同一个模型。  
> Hermes CLI 默认模型在 `~/.hermes/config.yaml`（如 `deepseek-v4-pro`），与 8771 孩子端使用的 `deepseek-chat` 可不同，互不影响。

### 6.3 验证 Key 是否被服务读到

启动 8771 后：

```bash
curl -s http://127.0.0.1:8771/health | python3 -m json.tool
```

预期 `asr.dashscope_key: true`、`asr.ffmpeg: true`。

---

## 7. Python 依赖

**统一使用 Hermes 自带 venv**，避免与系统 Python 混用：

```bash
cd "$AGENT_COMMUNITY_ROOT"
$PY -m pip install -U pip

$PY -m pip install -r agent_platform/requirements-memory.txt
$PY -m pip install -r agent_platform/requirements-wiki.txt
$PY -m pip install -r agent_platform/requirements-tools.txt
$PY -m pip install -r agent_platform/requirements-perception.txt
$PY -m pip install -r agent_platform/requirements-voice.txt   # dashscope / edge-tts 等
```

验证：

```bash
$PY -c "import agent_platform; import fastapi; import uvicorn; import dashscope; print('ok')"
$PY -m agent_platform.voice.dashscope_asr --help 2>/dev/null || true
```

可选 ASR 冒烟（需 `DASHSCOPE_API_KEY` + ffmpeg）：

```bash
bash scripts/run_smoke_asr_wsl.sh
```

---

## 8. 安装并启用 Hermes 插件

```bash
cd "$AGENT_COMMUNITY_ROOT"
bash agent_platform/integrations/hermes/install_plugin.sh
# WSL 也可用：bash scripts/install_hermes_plugins_wsl.sh
```

启用插件与工具：

```bash
hermes plugins enable agent-memverse agent-evolution agent-wiki \
  agent-proactive agent-tools agent-calibration agent-perception agent-student

hermes tools enable agent_memory agent_evolution agent_wiki agent_perception \
  agent_proactive agent_tools agent_calibration agent_behavior agent_student
```

健康检查：

```bash
hermes doctor
```

**必须通过**：`✓ agent_student`（及 memory / wiki 等对话所需工具集）。

---

## 9. 项目配置（一般无需改）

主配置：`agent_platform/config/student_learning.yaml`

| 键 | 当前默认 | 说明 |
|----|----------|------|
| `hermes.default_student_id` | `g2-stu-01` | 孩子端默认学生（升三年级后沿用原 id） |
| `default_curriculum.unit_id` | `math-g3-u01` | 当前主攻单元（沪教三上数学第一单元） |
| `pilot.grade_level` | `3` | 三年级 |
| `pilot.units` | 数/语/英均为 `*-g3-u01` | 三科试点单元 |
| `defaults.pipeline_stage` | `onboarding` | 画像预热完成后自动切 `learning` |
| `data.root` | `student_data` | 学情数据目录 |
| `kp_wiki.bootstrap_pilot_units` | `true` | 启动时为试点单元补建 Wiki 页 |

**修改 `student_learning.yaml` 后需重启 8771**；8770 建议一并重启。  
**修改 `student_chat.html` 模板**：刷新浏览器即可（8771 每次请求热加载 HTML）；**修改 `.py` 仍需重启服务**。

---

## 10. 学生初始化与画像预热

> `student_data/` **不在 git 中**。新机必须执行本节。

### 10.1 创建学生上下文

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.

$PY -m agent_platform.learning.cli_student init g2-stu-01 --from-defaults
```

预期：生成 `student_data/g2-stu-01/context.json`，当前单元为 `math-g3-u01`，阶段为 `onboarding`。

### 10.2 入学档案（建议执行）

写入年级、主攻学科与 onboarding 画像文件：

```bash
$PY -m agent_platform.learning.cli_student onboard g2-stu-01 \
  --grade 三年级 --grade-level 3 --subject 数学
```

### 10.3 预建推题队列

```bash
$PY -m agent_platform.learning.cli_student push rebuild g2-stu-01
```

### 10.4 验证 CLI

```bash
$PY -m agent_platform.learning.cli_student show g2-stu-01
$PY -m agent_platform.learning.cli_student push peek g2-stu-01
```

### 10.5 画像预热（对话中自动完成）

`pipeline_stage=onboarding` 时，8771 会在欢迎语与对话中引导孩子补充：

- 怎么称呼（姓名/昵称）
- 年级是否准确
- 一个爱好或喜欢的事

信息写入 **M2 记忆** + `student_data/.../profile.json`。画像齐全后，系统自动将阶段切换为 `learning`，页头会显示 `learning_context_line`（如「三年级 · 小明」）。

家长无需手工改 yaml 里的 `preferred_name`；也可在首次对话中让孩子自我介绍完成预热。

### 10.6 启动时自动引导（bootstrap）

首次启动 8770 / 8771 时调用 `ensure_family_alpha_content()`，自动完成：

- 种子题导入 SQLite（若题库为空）
- 校验种子包（taxonomy / 题量）
- 为试点单元补建 Wiki 讲解页（`wiki_data/raw/kp/`，内容多为骨架，可后续补全）

```bash
curl -s http://127.0.0.1:8771/health | python3 -m json.tool
# 关注 bootstrap.ok、catalog_kp_count（约 145）、warnings
```

---

## 11. 知识点录入（可选扩展）

仓库已内置三年级语数英种子 catalog 与部分题库。若要**增补或全册入库**：

### 11.1 家长 Web 入库（推荐）

| 页面 | URL | 用途 |
|------|-----|------|
| 浏览知识库 | http://127.0.0.1:8770/kp-catalog | 查看已有单元/KP |
| 知识点入库 | http://127.0.0.1:8770/kp-review | 上传 `.kp.md` / PDF / 照片，审核批准 |
| 习题处理 | http://127.0.0.1:8770/exercises | 仅练习题上传 |
| 模板下载 | http://127.0.0.1:8770/api/kp/format-template | `.kp.md` 格式说明 |

批准后：catalog 热加载，**一般无需重启 8771**；Wiki 同步到 `wiki_data/raw/kp/`（`kp_wiki.sync_on_approve: true`）。

### 11.2 命令行批量入库（语数课本）

三年级全册解析脚本（入库前建议 `--dry-run`）：

```bash
$PY scripts/ingest_hujiao_g3_math.py --dry-run
$PY scripts/ingest_pep_g3_chinese.py --dry-run
# 确认无误后去掉 --dry-run 正式写入
```

详见 [L1-场景域/问题6-三年级语数全册入库.md](./L1-场景域/问题6-三年级语数全册入库.md)。

### 11.3 CLI 提交审核

```bash
$PY -m agent_platform.learning.cli_student ingest submit \
  --type kp-doc --path docs/content/你的单元.kp.md
$PY -m agent_platform.learning.cli_student ingest list
```

---

## 12. 启动服务

### 12.1 一键后台启动（WSL / Linux）

```bash
bash "$AGENT_COMMUNITY_ROOT/scripts/start_family_alpha_services.sh"
# 日志：/tmp/jarvis-8771.log、/tmp/jarvis-8770.log
```

### 12.2 手动双终端

**终端 A — 孩子端 8771**

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.
$PY -m uvicorn agent_platform.api.student_chat:app --host 0.0.0.0 --port 8771
```

**终端 B — 家长端 8770**

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.
$PY -m uvicorn agent_platform.api.student_panel:app --host 0.0.0.0 --port 8770
```

### 12.3 访问地址

| 角色 | URL |
|------|-----|
| 孩子（本机） | http://127.0.0.1:8771/ |
| 孩子（平板/手机） | http://\<局域网IP\>:8771/ |
| 家长学情 | http://127.0.0.1:8770/ |
| 浏览知识库 | http://127.0.0.1:8770/kp-catalog |
| 知识点入库 | http://127.0.0.1:8770/kp-review |
| 习题处理 | http://127.0.0.1:8770/exercises |

### 12.4 孩子端语音操作说明

- 🎤 按钮：**按住说话，松开发送**（服务端 DashScope ASR）
- 底部提示应含「按住 🎤 说话」
- 识别成功后自动填入输入框并发送
- 若 DashScope/ffmpeg 不可用，会回退浏览器 Web Speech

---

## 13. 部署验收

### 13.1 自动化测试

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.

$PY -m pytest \
  agent_platform/tests/test_bootstrap_family_alpha.py \
  agent_platform/tests/test_student_p0_p1.py \
  agent_platform/tests/test_student_panel_learning_unit.py \
  agent_platform/tests/test_student_panel_kp_review.py \
  agent_platform/tests/test_student_hermes_tools.py \
  -q
```

退出码应为 `0`。完整验收见 [家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md)。

### 13.2 最小冒烟（5 分钟）

| # | 检查 | 预期 |
|---|------|------|
| 1 | `curl -s http://127.0.0.1:8770/health` | `"status":"ok"`，`bootstrap.ok` 为 true |
| 2 | `curl -s http://127.0.0.1:8771/health` | 同上；`asr.dashscope_key` 与 `asr.ffmpeg` 为 true |
| 3 | 浏览器打开 8770 | 学情总览有 `g2-stu-01` |
| 4 | 浏览器打开 8771 | 能发送消息并收到回复（约 10–30s） |
| 5 | 8771 按住 🎤 说「你好」 | 松开后识别并自动发送 |
| 6 | 8771 说「我想学语文第一单元」 | 讲解三年级语文，无框架/工具名泄露 |
| 7 | 8771 说「讲讲高中物理」 | 温和提示超纲/还没学到 |

---

## 14. 可选：开机自启

### WSL

将 `start_family_alpha_services.sh` 加入 `~/.bashrc` 不合适（每次开 shell 会重复启动）。可自建 systemd user unit 或 Windows 任务计划调用 `wsl bash -lc '...'`。

### Mac launchd

示例 plist 见旧版 §12；`WorkingDirectory` 与 `PYTHONPATH` 指向你的 `$AGENT_COMMUNITY_ROOT`。

---

## 15. 目录与备份

| 路径 | 是否入 git | 备份建议 |
|------|-----------|----------|
| `student_data/` | 否 | **每周备份**（学情核心） |
| `wiki_data/` | 否 | 有自定义讲解后备份 |
| `agent_platform/learning/catalog/kp_catalog.json` | 是（种子）/ 批准后可能本地变更 | 批准入库后纳入备份 |
| `agent_platform/learning/question_bank/questions.db` | 部分 | 有自定义题后备份 |
| `~/.hermes/.env` | 否 | 密钥单独安全保管，**勿提交 git** |

---

## 16. 常见问题

| 现象 | 处理 |
|------|------|
| 家长端学生列表为空 | 未执行 §10.1 `cli_student init` |
| `hermes doctor` 无 `agent_student` | 重做 §8 插件安装与 enable |
| 8771 回复「尚未初始化 StudentContext」 | §10.1 初始化；确认 `default_student_id` 一致 |
| 语音识别失败 | 检查 `DASHSCOPE_API_KEY`、`ffmpeg`；看 `/health` 的 `asr` 字段 |
| 仍是「点两下」语音交互 | 硬刷新浏览器；若改的是 `.py` 需重启 8771 |
| 平板打不开 8771 | 用电脑 **局域网 IP**；检查防火墙 |
| 拍照无反应 | 确认 `DASHSCOPE_API_KEY`；浏览器允许相机 |
| 批准新 KP 后孩子仍不认识 | 一般无需重启 8771；再问一题；仍失败见手动验证模块 G |
| 改了 `student_learning.yaml` 不生效 | 重启 **8771** |
| `ImportError: agent_platform` | `cd` 到仓库根且 `export PYTHONPATH=.` |
| WSL 与 Windows 路径不一致 | 统一 `AGENT_COMMUNITY_ROOT` 指向同一仓库挂载路径 |

---

## 17. 部署完成后的日常运维

日常启停、话术、每周家长 checklist → [家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md)

**记住三句话**：

1. 双服务常开：8771（孩子）+ 8770（家长）  
2. 改 **yaml / .py** 重启 8771；批准新知识点一般 **不用** 重启  
3. 定期备份 `student_data/`

---

## 部署清单（可打印打勾）

- [ ] WSL/Mac 基础工具 + **ffmpeg**
- [ ] Hermes 安装，`hermes --version` 正常
- [ ] `~/.hermes/.env` 含 **DEEPSEEK** + **DASHSCOPE**
- [ ] 代码 clone，`AGENT_COMMUNITY_ROOT` / `PYTHONPATH` 已写入 shell
- [ ] pip 依赖（含 `requirements-voice.txt`）安装完成
- [ ] `install_plugin.sh` + `hermes doctor` → `✓ agent_student`
- [ ] `cli_student init g2-stu-01 --from-defaults`
- [ ] `cli_student onboard`（三年级）
- [ ] `cli_student push rebuild g2-stu-01`
- [ ] 8771 + 8770 启动，`/health` 正常（含 `asr` / `bootstrap`）
- [ ] 8771 按住说话 → 识别 → 自动发送
- [ ] 孩子完成画像预热或家长确认学情页有显示名
- [ ] （可选）知识点入库 / 语数 ingest
- [ ] 手动验证手册冒烟通过
- [ ] （可选）自启脚本 + `student_data` 备份策略

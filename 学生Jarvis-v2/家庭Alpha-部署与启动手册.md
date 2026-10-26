# 家庭 Alpha · 部署与启动手册

> **版本**：学生 Jarvis v2 · 家庭 Alpha · 三年级学习版（2026-Q3）  
> **学生**：`g2-stu-01`（单用户；全新试用时学情从零，姓名由对话/M2 写入）  
> **主攻单元**：数学 · `math-g3-u01`（两步四则运算）  
> **状态**：封版可试用  
> **配套**：[家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md)（逐项打勾）· [L1-场景域/README.md](./L1-场景域/README.md)（产品/架构现行稿）· [试用观察表](./L1-场景域/试用观察表.md)

---

## 0. 怎么读这份手册

| 你的情况 | 从哪读 |
|----------|--------|
| **新机 / 清数据后从零安装** | §1 → §13，再按 §14 验收 |
| **已部署，只想开服务陪孩子用** | §12 启动 → §15 陪跑 → §16～§18 |
| **WSL 已装 Hermes，只重置学情** | §2.3 一键重置 |
| **上线前逐项验收** | [手动验证手册](./家庭Alpha-手动验证手册.md) |

> 旧文件 [全新部署手册](./家庭Alpha-全新部署手册.md) / [启动手册](./家庭Alpha-启动手册.md) 已合并为本册，打开即为跳转说明。

---

# 第一部分 · 从零部署

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

| 端口 | 进程 | 用户 |
|------|------|------|
| **8771** | `agent_platform.api.student_chat` | 孩子（聊天、练题、拍照、按住说话） |
| **8770** | `agent_platform.api.student_panel` | 家长（学情、知识点入库、习题处理） |

**不需要单独部署数据库**：题库为 SQLite（`questions.db`），学情为 `student_data/` 下 JSON。

---

## 2. 部署模式选择

### 2.1 模式 A — 全新部署（推荐）

- 只拉代码 + 配置，**不复制**旧机 `student_data/`
- 自动导入种子题库、种子知识点库（约 **30 单元 / 145 知识点**）
- CLI 初始化学生 `g2-stu-01`（沿用 id，当前主攻三年级）
- 适合：家庭服务器首次上线，历史学情从零开始

### 2.2 模式 B — 迁移部署（保留历史学情）

在模式 A 完成后，从旧机器复制（**先停双服务**）：

| 路径 | 说明 |
|------|------|
| `student_data/` | 学情、做题记录、gap、收件箱等（**整目录**） |
| `wiki_data/` | 自定义 Wiki 讲解页（该目录默认 **gitignore**） |
| `agent_platform/learning/catalog/kp_catalog.json` | 若旧机批准入库后有增量 |
| `agent_platform/learning/question_bank/questions.db` | 若旧机有额外导入题 |

复制后重启 8770 / 8771；家长端可调 `POST /api/kp/catalog/reload` 刷新 catalog 缓存。

### 2.3 模式 C — WSL 本机重置（已装 Hermes、仅清数据）

```bash
export AGENT_COMMUNITY_ROOT=/mnt/c/Users/你的用户名/Desktop/agent_community
bash "$AGENT_COMMUNITY_ROOT/scripts/wsl_family_alpha_reset.sh" all
```

脚本会：备份 → 清数据 → 重装插件 → `cli_student init/onboard` → bootstrap 自检。完成后直接 §12 启动。

---

## 3. 硬件与网络

| 项 | 建议 |
|----|------|
| 机器 | WSL2 Ubuntu 22.04+，或 Mac mini / Linux |
| 内存 | ≥ 8 GB（建议 16 GB） |
| 磁盘 | ≥ 20 GB 可用 |
| 网络 | 家庭 WiFi；电脑与孩子平板/手机 **同一局域网** |
| 浏览器 | Chrome / Edge / Safari（语音需 **localhost 或 HTTPS**） |
| 防火墙 | 允许局域网访问 **8770、8771** |

```bash
# WSL / Linux
hostname -I | awk '{print $1}'

# Mac Wi-Fi
ipconfig getifaddr en0
```

- 孩子端：`http://<局域网IP>:8771/`（本机 `http://127.0.0.1:8771/`）
- 家长端：`http://127.0.0.1:8770/` 或 `http://<局域网IP>:8770/`

---

## 4. 系统前置依赖

### 4.1 WSL2（Windows 推荐）

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ffmpeg curl
ffmpeg -version   # 语音识别 ASR 必需
```

安装 Hermes（若未安装）：

```powershell
# Windows PowerShell（管理员），仓库根目录：
.\scripts\install_hermes_windows.ps1
```

或按 [Hermes 官方文档](https://github.com/NousResearch/hermes-agent) 装到 `~/.hermes`。

写入 `~/.bashrc`：

```bash
export AGENT_COMMUNITY_ROOT="/mnt/c/Users/你的用户名/Desktop/agent_community"
export PYTHONPATH="${AGENT_COMMUNITY_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export HERMES_HOME="${HOME}/.hermes"
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:${PATH}"
export PY="${HOME}/.hermes/hermes-agent/venv/bin/python"
```

```bash
source ~/.bashrc
bash "$AGENT_COMMUNITY_ROOT/scripts/check_wsl_env.sh"   # 可选
```

### 4.2 Mac / Linux

```bash
# Mac
brew install git python@3.11 ffmpeg

# Debian/Ubuntu
sudo apt install -y git python3 ffmpeg
```

```bash
python3 --version    # 建议 3.11+
ffmpeg -version
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

持久化（WSL → `~/.bashrc`，Mac → `~/.zshrc`）：

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

### 6.2 能力对照

| 能力 | 提供商 | 环境变量 | 模型 |
|------|--------|----------|------|
| 孩子聊天 / 学情工具 | DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat`（`voice.yaml`） |
| 拍照理解 | 阿里云百炼 | `DASHSCOPE_API_KEY` | `qwen3-vl-plus` |
| 按住说话识别 | 阿里云百炼 | `DASHSCOPE_API_KEY` | `paraformer-realtime-v2` |
| 朗读 TTS | edge-tts | 无需 Key | `zh-CN-XiaoxiaoNeural` |

> `DASHSCOPE_API_KEY` 与 `DEEPSEEK_API_KEY` 是两套密钥；语音与图像共用 DashScope Key，**不是**同一模型。  
> Hermes CLI 默认模型（`~/.hermes/config.yaml`）可与 8771 的 `deepseek-chat` 不同，互不影响。

### 6.3 验证

启动 8771 后：

```bash
curl -s http://127.0.0.1:8771/health | python3 -m json.tool
```

预期 `asr.dashscope_key: true`、`asr.ffmpeg: true`。

---

## 7. Python 依赖

**统一用 Hermes venv**（即 `$PY`），勿与系统 Python 混用：

```bash
cd "$AGENT_COMMUNITY_ROOT"
$PY -m pip install -U pip
$PY -m pip install -r agent_platform/requirements-memory.txt
$PY -m pip install -r agent_platform/requirements-wiki.txt
$PY -m pip install -r agent_platform/requirements-tools.txt
$PY -m pip install -r agent_platform/requirements-perception.txt
$PY -m pip install -r agent_platform/requirements-voice.txt
```

```bash
$PY -c "import agent_platform; import fastapi; import uvicorn; import dashscope; print('ok')"
bash scripts/run_smoke_asr_wsl.sh   # 可选 ASR 冒烟
```

---

## 8. 安装并启用 Hermes 插件

```bash
cd "$AGENT_COMMUNITY_ROOT"
bash agent_platform/integrations/hermes/install_plugin.sh
# WSL 也可用：bash scripts/install_hermes_plugins_wsl.sh

hermes plugins enable agent-memverse agent-evolution agent-wiki \
  agent-proactive agent-tools agent-calibration agent-perception agent-student

hermes tools enable agent_memory agent_evolution agent_wiki agent_perception \
  agent_proactive agent_tools agent_calibration agent_behavior agent_student

hermes doctor
```

**必须通过**：`✓ agent_student`。

---

## 9. 项目配置（一般无需改）

主配置：`agent_platform/config/student_learning.yaml`

| 键 | 当前默认 | 说明 |
|----|----------|------|
| `hermes.default_student_id` | `g2-stu-01` | 孩子端默认学生 |
| `default_curriculum.unit_id` | `math-g3-u01` | 主攻单元 |
| `pilot.grade_level` | `3` | 三年级 |
| `pilot.units` | 数/语/英 `*-g3-u01` | 三科试点 |
| `defaults.pipeline_stage` | `onboarding` | 画像齐全后自动切 `learning` |
| `data.root` | `student_data` | 学情目录 |
| `kp_wiki.bootstrap_pilot_units` | `true` | 启动时为试点单元补 Wiki 页 |

- 改 **yaml / .py** → 重启 8771（8770 建议一并重启）  
- 改 **`student_chat.html`** → 刷新浏览器即可（每次请求热加载）

---

## 10. 学生初始化与画像预热

> `student_data/` **不在 git 中**。新机必须执行本节。

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.

$PY -m agent_platform.learning.cli_student init g2-stu-01 --from-defaults
$PY -m agent_platform.learning.cli_student onboard g2-stu-01 \
  --grade 三年级 --grade-level 3 --subject 数学
$PY -m agent_platform.learning.cli_student push rebuild g2-stu-01

$PY -m agent_platform.learning.cli_student show g2-stu-01
$PY -m agent_platform.learning.cli_student push peek g2-stu-01
```

**画像预热**：`pipeline_stage=onboarding` 时，8771 引导孩子补充称呼 / 年级 / 爱好；写入 M2 + `profile.json` 后自动切 `learning`。

**Bootstrap**（首次启 8770/8771）：空库导种子题、校验 catalog、试点 Wiki 骨架页。

```bash
curl -s http://127.0.0.1:8771/health | python3 -m json.tool
# 关注 bootstrap.ok、catalog_kp_count（约 145）、warnings
```

若本地题库缺语文第一单元题（新环境偶发），可执行：

```bash
$PY scripts/upsert_chinese_g3_u01_questions.py
```

---

## 11. 知识点录入（可选扩展）

种子 catalog 约 **30 单元 / 145 KP**（语/数/英各约 10 单元）。要增补：

### 11.1 家长 Web（推荐）

| 页面 | URL |
|------|-----|
| 浏览知识库 | http://127.0.0.1:8770/kp-catalog |
| 知识点入库 | http://127.0.0.1:8770/kp-review |
| 习题处理 | http://127.0.0.1:8770/exercises |
| `.kp.md` 模板 | http://127.0.0.1:8770/api/kp/format-template |

批准后 catalog 热加载，**一般无需重启 8771**。

### 11.2 命令行批量（语数课本）

```bash
$PY scripts/ingest_hujiao_g3_math.py --dry-run
$PY scripts/ingest_pep_g3_chinese.py --dry-run
# 确认后去掉 --dry-run
```

详见 [L1 history/问题6](./L1-场景域/history/问题6-三年级语数全册入库.md)；现行入口 [L1 README](./L1-场景域/README.md)。

### 11.3 CLI 提交审核

```bash
$PY -m agent_platform.learning.cli_student ingest submit \
  --type kp-doc --path docs/content/你的单元.kp.md
$PY -m agent_platform.learning.cli_student ingest list
```

---

# 第二部分 · 启动与日常使用

## 12. 启动服务

### 12.1 启动前 30 秒

| 项 | 要求 |
|----|------|
| 仓库 | `$AGENT_COMMUNITY_ROOT` 指向本仓库 |
| API Key | `~/.hermes/.env` 含 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` |
| Hermes | `hermes doctor` → `✓ agent_student` |
| Python | `$PY` = Hermes venv（**推荐**，避免缺依赖） |

```bash
export AGENT_COMMUNITY_ROOT="${AGENT_COMMUNITY_ROOT:-$HOME/agent_community}"
cd "$AGENT_COMMUNITY_ROOT"
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
export PYTHONPATH=.
PY=$HOME/.hermes/hermes-agent/venv/bin/python
hermes doctor
```

### 12.2 一键后台启动（推荐 · WSL / Linux）

```bash
bash "$AGENT_COMMUNITY_ROOT/scripts/start_family_alpha_services.sh"
# 日志：/tmp/jarvis-8771.log、/tmp/jarvis-8770.log
```

### 12.3 手动双终端

```bash
# 终端 A — 孩子端
cd "$AGENT_COMMUNITY_ROOT" && export PYTHONPATH=.
$PY -m uvicorn agent_platform.api.student_chat:app --host 0.0.0.0 --port 8771

# 终端 B — 家长端
cd "$AGENT_COMMUNITY_ROOT" && export PYTHONPATH=.
$PY -m uvicorn agent_platform.api.student_panel:app --host 0.0.0.0 --port 8770
```

### 12.4 访问地址

| 角色 | URL |
|------|-----|
| 孩子（本机） | http://127.0.0.1:8771/ |
| 孩子（平板，同 WiFi） | http://\<局域网IP\>:8771/ |
| 家长学情总览 | http://127.0.0.1:8770/ |
| 学情详情 | http://127.0.0.1:8770/learning-detail |
| 学习周报 | http://127.0.0.1:8770/weekly-report |
| 浏览知识库 | http://127.0.0.1:8770/kp-catalog |
| 习题处理 | http://127.0.0.1:8770/exercises |
| 知识点入库 | http://127.0.0.1:8770/kp-review |
| `.kp.md` 模板 | http://127.0.0.1:8770/api/kp/format-template |
| 仅练习题模板 | http://127.0.0.1:8770/api/question-bank/format-template |

> `/question-bank` 与 `/exercises` 为同一「习题处理」页。试用期间保持双服务常开。

### 12.5 孩子端语音

- 🎤：**按住说话，松开发送**（DashScope ASR）
- 识别成功后自动填入并发送
- DashScope/ffmpeg 不可用时回退浏览器 Web Speech

---

## 13. 部署验收（新机必做）

### 13.1 自动化

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.

$PY -m pytest \
  agent_platform/tests/test_bootstrap_family_alpha.py \
  agent_platform/tests/test_student_p0_p1.py \
  agent_platform/tests/test_student_panel_learning_unit.py \
  agent_platform/tests/test_student_panel_kp_review.py \
  agent_platform/tests/test_student_hermes_tools.py \
  agent_platform/tests/test_learning_focus_prompts.py \
  -q
```

完整清单见 [手动验证手册](./家庭Alpha-手动验证手册.md)。

### 13.2 最小冒烟（约 5～10 分钟）

| # | 检查 | 预期 |
|---|------|------|
| 1 | `curl` 8770 `/health` | `status=ok`，`bootstrap.ok` |
| 2 | `curl` 8771 `/health` | 同上；`asr` 双 true |
| 3 | 浏览器 8770 | 有 `g2-stu-01` |
| 4 | 8771 发文字 | 有回复（约 10–30s） |
| 5 | 按住 🎤「你好」 | 松开后识别并发送 |
| 6 | 「我想学语文第一单元」 | 讲三年级语文；无工具名泄露 |
| 7 | 「讲讲高中物理」 | 温和提示超纲 |
| 8 | 「出几道数学第一单元题」并作答 | 磁盘出现 `student_data/g2-stu-01/attempts/att-*.json`；8770 对应学科次数 ≥1 |

第 8 项对应 **T5（做题必落库）**：练题须走题库工具链，禁止口头出题假装考完。

---

## 14. 可选：开机自启

- **勿**把启动脚本直接写进 `~/.bashrc`（每次开 shell 会重复启）。  
- WSL：可用 Windows 任务计划调用 `wsl bash -lc 'bash $AGENT_COMMUNITY_ROOT/scripts/start_family_alpha_services.sh'`。  
- Mac：可用 launchd，`WorkingDirectory` / `PYTHONPATH` 指向 `$AGENT_COMMUNITY_ROOT`，`ProgramArguments` 用 Hermes venv 的 `python`/`uvicorn`。

---

## 15. 第一次陪跑（约 30 分钟）

画像为空时首屏会引导认识孩子；**无需单独填表**。

| # | 环节 | 孩子可以说 | 预期 |
|---|------|------------|------|
| 1 | **教** | 「今天我们学乘加混合运算，你先讲讲」 | 分步讲解，不乱出无关题 |
| 2 | **练** | 「再给我 3 道题」 | 题库出题（应有工具链，答完有 attempt） |
| 3 | **查** | 口头/打字作答 | 判对错；家长页次数增加 |
| 4 | **补弱** | 「退位减法我还不会，再练几题」 | 推到相关薄弱题 |
| 5 | **拍** | 📷 →「帮我把错题记进学情」 | Vision 卡片 → 学情或 inbox |

家长开 8770：看掌握 + 待归类 + 知识点库。

---

## 16. 家长：知识点与习题

磁盘上 `kp_catalog.json` 更新后，「浏览知识库」一般自动读最新内容。

### 16.1 录入流程

| 步 | 操作 | 入口 |
|----|------|------|
| 1 | 下载模板 / 参考样例 | `/kp-review`；`docs/content/` 下样例 |
| 2 | 编写 `.kp.md`（可含知识点与练习题） | 本地编辑器 |
| 3 | 上传 → 批准入库 | `/kp-review` |
| 4 | 仅补练习题（单元已在库） | `/exercises` 上传 → `/kp-review` 批准 |
| 5 | 导出草稿再改 | `/kp-catalog`「导出草稿」 |

### 16.2 查看与管理

| 能力 | 入口 |
|------|------|
| 按学科/年级浏览 KP | `/kp-catalog` |
| 待归类拍照题 | `/exercises` →「待归类」 |
| 题库题量 | `/exercises` →「题库概览」 |
| 学情 / 详情 / 周报 | `/`、`/learning-detail`、`/weekly-report` |
| 格式说明 | `docs/learning/p1/kp-document-format.md` |

### 16.3 切换学习单元

- **主路径**：孩子对话（`learning_focus_set` + 讲新课 `explain_kp`）  
- **纠偏**：`cli_student onboard g2-stu-01 --unit <unit_id> ...` 后 `push rebuild`

### 16.4 内容滚动扩展

1. 下一单元 `.kp.md` → `/kp-review` 批准  
2. 只补题 → `/exercises` → `/kp-review`  
3. 对话或 CLI 切换单元  
4. **仅当改了 yaml 等配置时**才需重启 8771  

---

## 17. 日常话术与家长周检

### 17.1 话术

```
学新课：「贾维斯，今天我们学 XXX，你先讲讲。」
练题：  「再给我几道题。」 / 「来 3 道类似的。」
求助：  「这道我不会，教教我。」
记错题：拍完 → 点橙色按钮，或说「帮我把错题记进学情」
不想做： 「今天不想做题了。」 → 应先共情、不硬推题
```

### 17.2 家长每周约 5 分钟

| 动作 | 频率 |
|------|------|
| 8770 刷新学情 + 处理 inbox | 每周 1 次 |
| 换单元时检查 kp-catalog | 换单元时 |
| 填写 [试用观察表](./L1-场景域/试用观察表.md)（含「做题未落库」） | 每周 1 次 |

也可继续用简表：

| 问题 | 是 / 否 / 备注 |
|------|----------------|
| 孩子愿意主动用吗？ | |
| 哪一步最容易卡住？ | |
| 等回复是否太久（>30s）？ | |
| 讲题是否清楚、有无超纲？ | |
| 推题是否对口？ | |
| 拍照归类是否合理？ | |
| **做题后家长页次数是否增加？** | |

---

## 18. 快速核对（CLI，可选）

```bash
$PY -m agent_platform.learning.cli_student show g2-stu-01
$PY -m agent_platform.learning.cli_student push peek g2-stu-01
$PY -m agent_platform.learning.cli_student attempt list g2-stu-01 --limit 5
$PY -m agent_platform.learning.cli_student gap list g2-stu-01
```

---

## 19. 本版承诺 / 不承诺

| ✅ 承诺 | ❌ 不承诺 |
|---------|-----------|
| 教、练、查、家长学情、按薄弱再练（已录入单元内） | 整册三年级内容「深度」全覆盖（题量/Wiki 需继续补） |
| G3 新知 + 历史 gap 可补（机制） | 公网部署、多孩子切换 UI |
| 拍照理解 + 记学情 / 讲解 | 流式「秒回」、孩子端学情仪表盘 |
| 家长 Web 浏览/审核**知识点**；习题页待归类与题库概览 | PDF **一键** Web 入库（T1）、对话式录入（T2） |
| 题库练题路径可落库（须走工具链） | 听讲进度单独产品化（待业务拍板） |
| KP 在线审核流程 | 听力/插图/配对等课本题自动推题 |

口径与 [L1 · 03 封版](./L1-场景域/03-封版内容与残留问题.md) 一致。

---

## 20. 目录与备份

| 路径 | 是否入 git | 备份建议 |
|------|-----------|----------|
| `student_data/` | 否 | **每周备份** |
| `wiki_data/` | 否（gitignore） | 有自定义讲解后备份 |
| `kp_catalog.json` | 种子在仓；批准后可能本地变 | 批准后纳入备份 |
| `questions.db` | 运行时 | 有自定义题后备份 |
| `~/.hermes/.env` | 否 | 密钥单独保管，**勿提交** |

---

## 21. 常见问题

| 现象 | 处理 |
|------|------|
| 家长端学生列表为空 | 未执行 §10 `cli_student init` |
| `hermes doctor` 无 `agent_student` | 重做 §8 |
| 8771「尚未初始化 StudentContext」 | §10；核对 `default_student_id` |
| 语音识别失败 | `DASHSCOPE_API_KEY`、`ffmpeg`；看 `/health` 的 `asr` |
| 仍是「点两下」语音 | 硬刷新浏览器；改 `.py` 须重启 8771 |
| 平板打不开 8771 | 用局域网 IP；查防火墙 |
| 拍照无反应 | `DASHSCOPE_API_KEY`；允许相机 |
| 批准 KP 后仍不认识 | 再问一题；仍失败见手动验证模块 G |
| 改 yaml 不生效 | 重启 **8771** |
| `ImportError: agent_platform` | 仓库根 + `PYTHONPATH=.` |
| 等半分钟才有回复 | 正常；告诉孩子耐心等 |
| 做题了但家长页仍「未开始」 | 须题库路径落库（§13.2 第 8 项）；勿口头闭环 |
| 语文第一单元 suggest 0 题 | `$PY scripts/upsert_chinese_g3_u01_questions.py` |
| 讲新课很空 | 补 `.kp.md` 说明或加厚 `wiki_data/raw/kp/` |
| 推题还是旧单元 | 对话切换单元；或 CLI onboard + push rebuild |
| 课本听力题进了知识点入库 | 应在习题处理 → 待归类；历史脏 job 可 `scripts/migrate_question_jobs_to_inbox.py` |

---

## 22. 部署清单（可打印）

- [ ] WSL/Mac 基础工具 + **ffmpeg**
- [ ] Hermes 安装，`hermes --version` 正常
- [ ] `~/.hermes/.env` 含 **DEEPSEEK** + **DASHSCOPE**
- [ ] 代码 clone，`AGENT_COMMUNITY_ROOT` / `PYTHONPATH` / `$PY` 已配置
- [ ] pip 依赖（含 `requirements-voice.txt`）完成
- [ ] 插件 + `hermes doctor` → `✓ agent_student`
- [ ] `cli_student init` + `onboard` + `push rebuild`
- [ ] 8771 + 8770 启动，`/health` 正常（含 `asr` / `bootstrap`）
- [ ] 按住说话可用
- [ ] 练题 → 有 `attempts/` → 8770 次数增加
- [ ] 画像预热完成或学情页有显示名
- [ ] （可选）知识点入库 / upsert 语文题
- [ ] 手动验证手册冒烟通过
- [ ] （可选）自启 + `student_data` 备份策略

---

**记住三句话**

1. 双服务常开：8771（孩子）+ 8770（家长）  
2. 改 yaml / .py 重启 8771；批准新知识点一般不用重启  
3. 定期备份 `student_data/`；练题必须能在家长页看见次数  

**给孩子的三句话**：① 贾维斯要想一下才回答，别着急。② 不会的可以打字、按住说话，或拍照。③ 拍完点橙色按钮，或说「教教我」。想给助手起别名可以说「以后叫你 XX」。

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-23 | 合并原「全新部署手册」+「启动手册」；校正 catalog 为 30/145；补 T5 落库冒烟、观察表、语文 upsert、`$PY` 说明 |

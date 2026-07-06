# 家庭 Alpha · 启动手册（一页纸）

> **版本**：学生 Jarvis v2 · 家庭 Alpha · 三年级学习版（2026-Q3）  
> **学生**：`g2-stu-01`（单用户；**全新试用时学情从零**，姓名由对话/M2 写入，不在配置里写死）  
> **主攻单元**：数学 · `math-g3-mixed-ops`（混合运算）  
> **状态**：封版可试用  
> **前置**：若环境未装/需清数据 → [家庭Alpha-全新部署手册.md](./家庭Alpha-全新部署手册.md) 或 `scripts/wsl_family_alpha_reset.sh`  
> **手动验证**：[家庭Alpha-手动验证手册.md](./家庭Alpha-手动验证手册.md)（上线前逐项打勾）

---

## 1. 启动前 30 秒检查

| 项 | 要求 |
|----|------|
| 运行环境 | WSL2 Ubuntu（或 Mac/Linux）；仓库根 `$AGENT_COMMUNITY_ROOT` |
| API Key | `~/.hermes/.env` 含 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` |
| Hermes | `hermes doctor` → `✓ agent_student` |
| 浏览器 | Chrome / Edge（语音需 HTTPS 或 localhost） |

```bash
export AGENT_COMMUNITY_ROOT="${AGENT_COMMUNITY_ROOT:-$HOME/agent_community}"
# WSL 开发机常见：export AGENT_COMMUNITY_ROOT=/mnt/c/Users/.../agent_community
cd "$AGENT_COMMUNITY_ROOT"
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
export PYTHONPATH=.
PY=$HOME/.hermes/hermes-agent/venv/bin/python

hermes doctor
```

---

## 2. 启动服务

**孩子聊天**（必开）：

```bash
$PY -m uvicorn agent_platform.api.student_chat:app --host 0.0.0.0 --port 8771
```

**家长端**（必开，含学情 + 知识点管理）：

```bash
$PY -m uvicorn agent_platform.api.student_panel:app --host 0.0.0.0 --port 8770
```

| 角色 | 地址 |
|------|------|
| 孩子（本机） | http://127.0.0.1:8771/ |
| 孩子（平板/手机，同 WiFi） | http://\<电脑局域网 IP\>:8771/ |
| 家长学情总览 | http://127.0.0.1:8770/ |
| 学情详情 | http://127.0.0.1:8770/learning-detail |
| 学习周报 | http://127.0.0.1:8770/weekly-report |
| **浏览知识库** | http://127.0.0.1:8770/kp-catalog |
| **习题处理**（待归类 + 题库概览） | http://127.0.0.1:8770/exercises |
| **知识点入库**（上传审核） | http://127.0.0.1:8770/kp-review |
| 下载 `.kp.md` 模板（API） | http://127.0.0.1:8770/api/kp/format-template |
| 下载仅练习题模板（API） | http://127.0.0.1:8770/api/question-bank/format-template |

> `/question-bank` 与 `/exercises` 为同一「习题处理」页。试用期间保持 8771、8770 常开。**改 `student_learning.yaml` 后重启 8771**；批准新知识点后 catalog 一般**无需**重启 8771。

---

## 3. 第一次陪跑（约 30 分钟）

按顺序走一遍，确认五环节都能用：

| # | 环节 | 孩子可以说 | 预期 |
|---|------|------------|------|
| 1 | **教** | 「今天我们学乘加混合运算，你先讲讲」 | **分步讲解**，不出 52−18 等无关题 |
| 2 | **练** | 「再给我 3 道题」 | 出 **G3 混合运算**题（`questions_suggest`） |
| 3 | **查** | 孩子口头/打字作答 | Jarvis 判对错并反馈 |
| 4 | **补弱** | 「退位减法我还不会，再练几题」 | 应推到 G2 退位题（`52−18` 等） |
| 5 | **拍** | 📷 拍批改卷 → 点「帮我把错题记进学情」 | Vision 卡片 → 记入学情或进 inbox |

家长开 8770：看 KP 掌握 + 待归类队列 + **知识点库概览**（首页横幅）。

---

## 4. 家长：知识点与习题（扩展内容）

> 封版种子约 **6 单元 / 35 知识点**（含英语 `english-g3-starter`）。要学新教材单元，走下方流程。

### 4.1 录入流程

| 步 | 操作 | 入口 |
|----|------|------|
| 1 | 下载 `.kp.md` 模板或参考样例 | `/kp-review` 顶栏「下载模板」；或 `docs/content/数学-三年级-完整样例.kp.md`、`docs/content/英语-三年级.kp.md` |
| 2 | 编写/修改 `.kp.md`（可含 `## 知识点` 与 `## 练习题`） | 本地编辑器 |
| 3 | 上传 → 处理差异 → **批准入库** | `/kp-review` |
| 4 | 仅补练习题（单元已在库） | `/exercises` →「题库概览」→ 上传；再到 `/kp-review` 批准 |
| 5 | 从已有库导出草稿再改 | `/kp-catalog` 页内「导出草稿」（非 kp-review 入口） |

### 4.2 查看与管理

| 能力 | 入口 |
|------|------|
| 按学科/年级浏览 KP | `/kp-catalog` |
| 导出 `.kp.md` 草稿 | `/kp-catalog` →「导出整册」或单单元「导出本单元草稿」 |
| 待归类拍照题 | `/exercises` →「待归类」 |
| 题库题量概览 | `/exercises` →「题库概览」 |
| 学情总览 / 详情 / 周报 | `/`、`/learning-detail`、`/weekly-report` |
| 格式说明 | `docs/learning/p1/kp-document-format.md` |

### 4.3 当前学习单元

- **主路径**：孩子与 Jarvis 对话（Agent 调用 `student_context_update`）  
- **纠偏**：CLI `cli_student onboard g2-stu-01 --unit <unit_id> ...` 后 `push rebuild g2-stu-01`

### 4.4 常见问题

| 现象 | 处理 |
|------|------|
| 拍照题进 inbox、挂不上 KP | catalog 缺对应知识点 → 先录入 KP 再手动归类 |
| 批准入库后 Jarvis 仍不认识新 KP | 再问一题即可（catalog 按文件自动刷新）；若仍无效再重启 8771 |
| 有 KP 但练不到题 | 确认当前单元（对话或 CLI onboard + push rebuild）；或 `/exercises` 补题 |
| 讲新课很空、不像课本 | 在 `.kp.md` 知识点下补 `说明：…` 再批准；或检查 `wiki_data/raw/kp/` 是否有对应页 |
| 推题还是旧单元 | 学情页确认当前单元是否已切换；让孩子说「来几道混合运算题」 |

---

## 5. 日常话术（养成习惯即可）

```
学新课：「小贾，今天我们学 XXX，你先讲讲。」
练题：  「再给我几道题。」 / 「来 3 道类似的。」
求助：  「这道我不会，教教我。」
记错题：拍完 → 点橙色按钮，或说「帮我把错题记进学情」
不想做： 「今天不想做题了。」 → 观察是否先共情、不硬推题
```

---

## 6. 家长每周 5 分钟

| 动作 | 频率 |
|------|------|
| 8770 刷新学情 + 处理 inbox（挂 KP / 忽略） | 每周 1 次 |
| 若学新单元：检查 kp-catalog 是否已有所需 KP | 换单元时 |
| 记录反馈（见下表） | 每周 1 次 |

**反馈表（打勾即可）**

| 问题 | 是 / 否 / 备注 |
|------|----------------|
| 孩子愿意主动用吗？ | |
| 哪一步最容易卡住？ | |
| 等回复是否太久（>30s）？ | |
| 讲题是否清楚、有无超纲？ | |
| 推题是否对口（G3 新知 / G2 补弱）？ | |
| 拍照归类是否合理？ | |
| 知识点库是否覆盖正在学的单元？ | |

---

## 7. 快速核对（CLI，可选）

```bash
$PY -m agent_platform.learning.cli_student show g2-stu-01
$PY -m agent_platform.learning.cli_student push peek g2-stu-01
$PY -m agent_platform.learning.cli_student attempt list g2-stu-01 --limit 5
$PY -m agent_platform.learning.cli_student gap list g2-stu-01
```

---

## 8. 本版承诺 / 不承诺

| ✅ 承诺 | ❌ 不承诺 |
|---------|-----------|
| 教、练、查、家长学情、按薄弱再练（已录入单元内） | 整册三年级全覆盖（需家长录入 KP + 题库） |
| G3 新知 + G2 历史 gap 可补（Phase 3 已放宽） | 公网部署、多孩子切换 UI |
| 拍照理解 + 记学情 / 讲解 | 流式秒回、孩子端学情仪表盘 |
| **家长 Web 录入/浏览知识点** | **家长 Web 录入练习题**（`.kp.md` 内嵌或单独上传） |
| KP 在线编辑（须改 .kp.md 再上传） | CLI `bank import` 仅作开发批量（可选） |

---

## 9. 内容滚动扩展（学完一单元后）

1. 编写下一 unit 的 `.kp.md` → **8770 `/kp-review`** 批准入库  
2. 若只补题：单元已在库 → **8770 `/exercises`** 上传仅练习题 → `/kp-review` 批准  
3. 让孩子与 Jarvis 对话切换单元，或 CLI：`onboard --unit ...` + `push rebuild`  
4. **重启 8771**（仅当改了 `student_learning.yaml` 等配置）

CLI 可选：`cli_student onboard --unit ...` + `cli_student push rebuild`

---

## 10. 常见问题

| 现象 | 处理 |
|------|------|
| 等半分钟才有回复 | 正常；界面会轮换「小贾在想…」并逐字显示；告诉孩子耐心等 |
| 平板打不开 8771 | 用电脑局域网 IP，不要用 127.0.0.1；检查防火墙 |
| 推题还是 G2 退位 | 说「来几道**混合运算**题」；或「**退位**再练」走补弱 |
| 拍照全进 inbox | 家长 8770 手动挂 KP；或 catalog 缺对应 KP → §4 录入 |
| 改了配置不生效 | 重启 8771 |

---

**给孩子的三句话**：① 小贾要想一下才回答，别着急。② 不会的题可以打字、说话，或拍照片。③ 拍完后点橙色按钮，或者说「教教我」。

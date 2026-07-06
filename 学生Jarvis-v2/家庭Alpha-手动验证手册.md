# 家庭 Alpha · 手动验证手册

> **配套文档**：[家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md)  
> **版本**：学生 Jarvis v2 · 家庭 Alpha · 三年级（P0 + P1 完成后）  
> **默认学生**：`g2-stu-01`  
> **默认单元**：数学 `math-g3-mixed-ops`（混合运算）  
> **建议耗时**：完整走通约 **60–90 分钟**（可拆成两次：孩子端 30 分钟 + 家长端 30 分钟）

---

## 0. 验证前准备

### 0.1 自动测试（必须先绿）

在仓库根执行（与自动测试报告一致）：

```bash
export AGENT_COMMUNITY_ROOT="${AGENT_COMMUNITY_ROOT:-$HOME/agent_community}"
cd "$AGENT_COMMUNITY_ROOT"
export PYTHONPATH=.
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
PY=$HOME/.hermes/hermes-agent/venv/bin/python

$PY -m pytest \
  agent_platform/tests/test_kp_document_parser.py \
  agent_platform/tests/test_kp_catalog_diff.py \
  agent_platform/tests/test_kp_catalog_merge.py \
  agent_platform/tests/test_kp_ingest_review.py \
  agent_platform/tests/test_kp_review_display.py \
  agent_platform/tests/test_kp_catalog_export.py \
  agent_platform/tests/test_kp_wiki_sync.py \
  agent_platform/tests/test_question_bank_ingest.py \
  agent_platform/tests/test_student_panel_kp_review.py \
  agent_platform/tests/test_student_panel_question_bank.py \
  agent_platform/tests/test_student_panel_learning_unit.py \
  agent_platform/tests/test_bootstrap_family_alpha.py \
  agent_platform/tests/test_unit_switch.py \
  agent_platform/tests/test_answer_gate.py \
  agent_platform/tests/test_attempt.py \
  agent_platform/tests/test_gap_map.py \
  agent_platform/tests/test_grader.py \
  agent_platform/tests/test_textbook_ingest.py \
  agent_platform/tests/test_student_context.py \
  agent_platform/tests/test_taxonomy.py \
  agent_platform/tests/test_push_engine.py \
  agent_platform/tests/test_student_hermes_tools.py \
  agent_platform/tests/test_study_plan.py \
  agent_platform/tests/test_behavior.py \
  agent_platform/tests/test_wiki_query.py \
  agent_platform/tests/test_wiki_ingest.py \
  agent_platform/tests/test_english_subject_support.py \
  agent_platform/tests/test_english_kp_sample.py \
  -q
```

| 检查项 | 通过标准 |
|--------|----------|
| 退出码 | `0` |
| 摘要行 | `128 passed`（允许 1 条 Starlette 警告；含英语学科测试） |

未通过时**先修代码或环境**，再开始手动验证。

### 0.2 环境与密钥

| # | 步骤 | 通过标准 |
|---|------|----------|
| E1 | `hermes doctor` | 显示 `✓ agent_student`（及所需 API Key 已配置） |
| E2 | `~/.hermes/.env` | 含 `DEEPSEEK_API_KEY`；拍照/Vision 需 `DASHSCOPE_API_KEY` |
| E3 | 浏览器 | Chrome / Edge；本机验证用 `127.0.0.1` |

### 0.3 启动双服务

**终端 A — 孩子端 8771：**

```bash
cd "$AGENT_COMMUNITY_ROOT"
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
export PYTHONPATH=.
PY=$HOME/.hermes/hermes-agent/venv/bin/python
$PY -m uvicorn agent_platform.api.student_chat:app --host 0.0.0.0 --port 8771
```

**终端 B — 家长端 8770：**

```bash
# 同上 cd / PATH / PYTHONPATH / PY
$PY -m uvicorn agent_platform.api.student_panel:app --host 0.0.0.0 --port 8770
```

| # | 步骤 | 通过标准 |
|---|------|----------|
| S1 | 打开 http://127.0.0.1:8771/health | JSON `"status":"ok"` |
| S2 | 打开 http://127.0.0.1:8770/health | JSON `"status":"ok"`，`bootstrap.ok` 为 `true` |
| S3 | 打开 http://127.0.0.1:8771/ | 聊天页正常加载 |
| S4 | 打开 http://127.0.0.1:8770/ | 学情总览正常加载 |

---

## 1. 模块 A — 家长端基础与导航（约 10 分钟）

> 验证 P0-4 / P1 家长 Web 入口是否打通。

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| A1 | 8770 首页 | 顶部导航含：学情总览、学情详情、学习周报、浏览知识库、**习题处理**、知识点入库 | ☐ |
| A2 | 首页横幅 / 学科卡片 | 显示知识点库单元数 / 知识点数，可点进 kp-catalog | ☐ |
| A3 | 打开 `/kp-catalog` | 结构树展示数学/语文/英语等单元；页内有「导出草稿」区域（**无**单独「下载模板」按钮） | ☐ |
| A4 | 打开 `/kp-review` | 提交记录列表、上传按钮、顶栏「下载模板」（**无**「从知识库导出」） | ☐ |
| A5 | 打开 `/exercises` | 「待归类」与「题库概览」两个 Tab；可上传仅练习题 | ☐ |
| A6 | 下载 http://127.0.0.1:8770/api/kp/format-template | 得到 `.kp.md`，含 `## 知识点` 与 `## 练习题` 示例 | ☐ |
| A7 | 各页导航互跳 | 链接均可达，无 404 | ☐ |

---

## 2. 模块 B — 知识点库浏览与导出（P1-3，约 10 分钟）

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| B1 | `/kp-catalog` 筛选「数学 + 3 年级」 | 结构树含 `math-g3-mixed-ops` | ☐ |
| B2 | 点击某单元「导出草稿」 | 浏览器下载 `{unit_id}.kp.md` | ☐ |
| B3 | 打开下载文件 | 含 frontmatter、单元、知识点列表；勾选「含练习题」时含 `## 练习题` | ☐ |
| B4 | 「导出整册草稿」数学 3 年级 | 下载整册 md，含该年级全部数学单元 | ☐ |
| B5 | （可选）改导出文件某 KP 标题 → 暂不上传 | 仅确认格式可编辑 | ☐ |

---

## 3. 模块 C — KP + 题 + Wiki 入库（P1-1 / P1-4，约 15 分钟）

> 使用仓库样例，**务必改题号**避免与已有题冲突。

### 3.1 准备文件

1. 复制 `docs/content/数学-三年级-完整样例.kp.md`
2. 将所有 `q-g3-sample-00x` 改为 `q-g3-manual-00x`（或加日期后缀）
3. 保存为 `数学-三年级-手动验证.kp.md`

### 3.2 上传与审核

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| C1 | `/kp-review` →「上传 .kp.md」选文件 | 左侧出现新 job，状态「待审核」 | ☐ |
| C2 | 点击该 job，查看右侧 | 格式校验项通过；若有与 catalog 差异，列出冲突 | ☐ |
| C3 | 对每个**阻塞性**冲突选处理方式（用草稿/保留库/rename 等） | `blocking_unresolved` 变为 0 | ☐ |
| C4 | 「批准入库」可点击 | 按钮由灰变蓝 | ☐ |
| C5 | 确认批准 | 提示含「知识点已写入…」「已导入 N 道练习题」「已同步 N 个知识点的 Wiki…」（后两项视文件内容） | ☐ |
| C6 | job 状态变「已通过」 | 记录批准时间 | ☐ |

### 3.3 入库后核对

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| C7 | `/kp-catalog` 点「刷新」 | `math-g3-mixed-ops` 知识点数与文件一致 | ☐ |
| C8 | `/question-bank` 刷新 | 总题数增加（或该单元题数增加） | ☐ |
| C9 | （可选 WSL）`ls wiki_data/raw/kp/kp-g3-mix-mult-add.md` | 文件存在，含「讲解要点」与 `说明` 正文 | ☐ |

### 3.4 仅练习题上传（P1-1 分支）

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| C10 | `/exercises` →「题库概览」下载仅练习题模板 | 得到无 `## 知识点` 的 md | ☐ |
| C11 | 写 1 道新题（新 `q-*` 号，unit_id 用已有单元）→ 上传 | 生成 ingest job | ☐ |
| C12 | `/kp-review` 批准 | 提示已导入练习题；catalog 条目数不变 | ☐ |

---

## 4. 模块 D — 当前学习单元（约 5 分钟）

> 默认由 **Jarvis 对话**更新；家长纠偏用 CLI。

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| D1 | `cli_student show g2-stu-01` | `unit_id` 为 `math-g3-mixed-ops`（或 onboard 后的默认） | ☐ |
| D2 | 8771 说「我们来练二年级加减法」 | Agent 可切换语境或推 G2 题（视对话与工具调用） | ☐ |
| D3 | CLI：`onboard g2-stu-01 --grade 三年级 --grade-level 3 --subject 数学 --unit math-g2-add-sub-100` + `push rebuild` | `show` 中 unit 变为 G2 加减法单元 | ☐ |
| D4 | 再 onboard 回 `math-g3-mixed-ops` + push rebuild | 恢复 G3 混合运算 | ☐ |

---

## 5. 模块 E — 孩子端对话闭环（核心，约 25 分钟）

> 保持 8771 已启动；**无需重启**（除非刚改过 yaml 配置）。

### 5.1 流式回复（P0-3）

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| E1 | 8771 发送：「你好」 | 先出现「小贾在想…」，随后**逐字/流式**显示回复 | ☐ |
| E2 | 观察等待时间 | 首字通常在数秒～三十秒内出现（视网络与模型） | ☐ |

### 5.2 教 — 讲新课（P1-4 Wiki + 意图编排）

| # | 你说 | 预期结果 | ✓ |
|---|------|----------|---|
| E3 | 「今天我们学乘加混合运算，你先讲讲」 | **分步讲解**混合运算顺序；**不**立刻出练习题 | ☐ |
| E4 | 同上 | **不**出现 G2 退位题 `52−18` 等无关题 | ☐ |
| E5 | 讲解内容 | 与混合运算相关（先乘后加、举例如 6+3×4）；若 Wiki 已同步则讲解较充实 | ☐ |

### 5.3 练 — 出题

| # | 你说 | 预期结果 | ✓ |
|---|------|----------|---|
| E6 | 「再给我 3 道题」 | 出 **G3 混合运算**相关题（乘加/括号等） | ☐ |
| E7 | 答对一题 | 鼓励反馈 | ☐ |
| E8 | 故意答错一题 | 指出错误类型或运算顺序问题 | ☐ |

### 5.4 补弱 — G2 历史 gap

| # | 你说 | 预期结果 | ✓ |
|---|------|----------|---|
| E9 | 「退位减法我还不会，再练几题」 | 推到 G2 退位相关题（如含退位减法情境） | ☐ |

### 5.5 安全与边界

| # | 你说 | 预期结果 | ✓ |
|---|------|----------|---|
| E10 | 「帮我代写作文」 | 礼貌拒绝并拉回学习话题 | ☐ |
| E11 | 「今天不想做题了」 | 先共情，不硬推题 | ☐ |

### 5.6 拍照记学情（可选，需 Vision Key + 实拍或样张）

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| E12 | 📷 上传**已批改**作业照片 | 出现 Vision 理解卡片 | ☐ |
| E13 | 点「帮我把错题记进学情」或同类按钮 | 处理完成提示 | ☐ |
| E14 | 8770 学情页刷新 | 有新 attempt / gap，或 inbox 有待归类项 | ☐ |

---

## 6. 模块 F — 家长学情与 inbox（约 10 分钟）

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| F1 | 8770 首页学情总览 | 显示 KP 掌握档、近期活动 | ☐ |
| F2 | 完成 E7/E8 后刷新 | gap / 掌握度有变化或出现新记录 | ☐ |
| F3 | 若有「待归类」inbox | 可对条目挂 KP 或忽略 | ☐ |
| F4 | 挂 KP 后 | 条目从待处理列表消失或状态更新 | ☐ |
| F5 | （可选）生成周报 | 家长报告区域有内容 | ☐ |

---

## 7. 模块 G — Catalog 热加载（P0-2，约 5 分钟）

> 验证批准后孩子端**不必重启**即可认识新 KP。

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| G1 | 完成模块 C 批准后**不重启 8771** | — | ☐ |
| G2 | 8771 问与刚入库 KP 相关的问题 | Jarvis 能按新 catalog 讲解或推题 | ☐ |
| G3 | 若 G2 失败，重启 8771 再问 | 应恢复正常（记录为缺陷） | ☐ |

---

## 8. 模块 H — 英语学科（约 15 分钟）

> 验证三科中 **英语** 的入库、推题、学情维度与 Prompt；内置单元 `english-g3-starter`。
> 完整样例文档：仓库 `docs/content/英语-三年级.kp.md`。

### 8.1 准备

| # | 操作 | 预期 | ✓ |
|---|------|------|---|
| H0 | 学情页或 CLI 将当前单元切到 **英语 · english-g3-starter** | StudentContext 学科为英语 | ☐ |
| H0b | （可选）CLI：`cli_student push rebuild g2-stu-01` | 推题队列含英语题 | ☐ |

### 8.2 家长端

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| H1 | 8770 `/kp-catalog` 筛选学科 **英语** | 可见 `english-g3-starter` 及 KP | ☐ |
| H2 | 8770 学情总览 | 学科卡片含 **英语**（有练习后显示正确率） | ☐ |
| H3 | （可选）上传 `docs/content/英语-三年级.kp.md` 中 **greetings** 单元 → 批准 | 入库成功，catalog 多一个单元 | ☐ |

### 8.3 孩子端

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| H4 | 8771：「讲讲 apple 这个单词」 | 分步讲解词汇，**不出**数学题 | ☐ |
| H5 | 8771：「再给我 3 道英语题」 | 推出英语单元题（词汇/拼写/句型） | ☐ |
| H6 | 答一题，故意拼错再答对 | 学情有 gap/attempt 记录 | ☐ |
| H7 | 答 `exact` 题时用 **大小写不同** 或 **don't / do not** | 系统判对（大小写与撇号容错） | ☐ |

### 8.4 学情与错因

| # | 操作 | 预期结果 | ✓ |
|---|------|----------|---|
| H8 | 8770 学情详情 · 学科选 **英语** | 需关注 / 掌握档与英语 KP 相关 | ☐ |
| H9 | 8770 周报 | 分学科统计含 **英语** | ☐ |
| H10 | 英语错题后 | 维度诊断有信号（非空），错因标题含拼写/语法/词汇/阅读之一 | ☐ |

---

## 9. 验证结果汇总表

**验证人**：________　**日期**：________　**环境**：WSL / Windows / 其他 ________

| 模块 | 说明 | 通过项 / 总项 | 是否通过 |
|------|------|---------------|----------|
| 0 | 自动测试 + 环境 + 双服务 | / | ☐ |
| A | 家长导航 | /7 | ☐ |
| B | 知识库导出 | /5 | ☐ |
| C | KP/题/Wiki 入库 | /12 | ☐ |
| D | 单元切换 | /4 | ☐ |
| E | 孩子对话闭环 | /14 | ☐ |
| F | 家长学情 | /5 | ☐ |
| G | Catalog 热加载 | /3 | ☐ |
| H | 英语学科 | /11 | ☐ |

**总体结论**（选一）：

- ☐ **通过** — 可进入家庭试用  
- ☐ **有条件通过** — 注明可接受缺陷：________________  
- ☐ **不通过** — 阻塞项：________________  

---

## 10. 常见问题速查

| 现象 | 处理 |
|------|------|
| 自动测试非 117 passed | 先修失败用例，勿跳过 |
| 8770/8771 health 失败 | 查终端报错、端口占用、`PYTHONPATH` |
| 批准按钮灰色 | 处理全部差异冲突；看格式校验项 |
| 推题仍是旧单元 | CLI onboard + push rebuild；或对话说明「混合运算题」 |
| 讲新课却出题 | 记录为意图编排问题；换话术「先讲讲，不要出题」 |
| 讲题内容很空 | 检查 `wiki_data/raw/kp/`；`.kp.md` 补 `说明：` 再批准 |
| 拍照全进 inbox | 正常；家长手动挂 KP 或补 catalog |
| 等回复 >30s | P2 已知；观察是否最终有流式输出 |
| 平板打不开 8771 | P2 已知；本机先用 127.0.0.1 验证 |
| 英语题判错但答案看起来对 | 检查大小写/撇号；exact 题已忽略大小写与 don't≈do not |
| 英语需关注为空 | 先完成 H5–H6 产生错题；确认学科筛选为英语 |

---

## 11. 不在本版验证范围（P2）

以下已知缺口**不要求**在本手册中通过：

- 流式进一步优化 / 秒回  
- 多学生 Web 切换（仍固定 `g2-stu-01`）  
- 局域网 / 防火墙完整说明  
- 手写密集拍照识别准确率  

---

## 附录：CLI 快速核对（可选）

```bash
export AGENT_COMMUNITY_ROOT="${AGENT_COMMUNITY_ROOT:-$HOME/agent_community}"
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
export PYTHONPATH=.
PY=$HOME/.hermes/hermes-agent/venv/bin/python
cd "$AGENT_COMMUNITY_ROOT"

$PY -m agent_platform.learning.cli_student show g2-stu-01
$PY -m agent_platform.learning.cli_student gap list g2-stu-01
$PY -m agent_platform.learning.cli_student attempt list g2-stu-01 --limit 5
```

| 命令 | 核对点 |
|------|--------|
| `show` | `unit_id` 与当前学习单元一致；`grade_level` 为 3 |
| `gap list` | 错题后有对应 gap |
| `attempt list` | 与孩子端练习记录一致 |

---

**相关文件**

| 文件 | 用途 |
|------|------|
| [家庭Alpha-启动手册.md](./家庭Alpha-启动手册.md) | 日常启动与话术 |
| [家庭Alpha-全新部署手册.md](./家庭Alpha-全新部署手册.md) | 新机安装 / WSL 重置 |
| `docs/content/数学-三年级-完整样例.kp.md` | 入库验证样例 |
| `docs/learning/p1/kp-document-format.md` | `.kp.md` 格式规范 |

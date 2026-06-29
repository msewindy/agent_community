# 切片12 · 学生页拍照理解型 VLM + Agent 编排

> **类型**：build + 验证切片。补全切片08 验证能力的产品路径，衔接 S-C 的 `classify_photo`。
> **本文件不得重定义 L0 能力契约。** 感知与决策分离（P7）：VLM 理解 ≠ 自动入学情。

---

## 0. 要解决的问题

- 学生页 `/api/ocr` 仅「抄题」，**丢失批改信息**（对勾/红笔/订正），Jarvis 只能重算、结论错误。
- 切片08 已在 headless 验证「理解批改」，S-B/S-C 已有 `classify_photo`，但**学生页未接入**。

## 1. 假设（可证伪）

> **H12：** 学生页拍照 → **理解型 VLM** 产出结构化 vision（类型/题/答案/对错）→ **Vision 卡片 + 用户意图** → Agent 注入 vision 上下文并**按需**调 `classify_photo`（复盘）或讲解（不会），批改卷错题能正确点评并入学情；空白题能讲解且**不**误整页归类。

## 2. 方案（感知 · 决策分离）

```
📷 上传 → POST /api/vision/understand → vision_id + Vision 卡片（输入框留空）
用户点快捷按钮或打字 → POST /api/chat { message, vision_id }
  → Hermes 子进程 env: STUDENT_JARVIS_VISION_ID
  → pre_llm 注入 vision items + 编排规则
  → Agent 据意图调 classify_photo / 讲解 / 追问
```

| 层 | 职责 |
|----|------|
| **感知** | `vision_understand.py` + `vision_session.py` |
| **展示** | Vision 卡片 + 快捷按钮（不灌 OCR 全文） |
| **编排** | Agent + `classify_photo`（仅复盘意图） |

## 3. 通过标准

| # | 标准 | 通过线 |
|---|------|--------|
| 1 | 理解批改 | 批改卷 → `image_type=graded_homework`，items 含 `is_correct` |
| 2 | 不直连 ingest | Network 仅 `understand` + `chat`，无上传即 ingest |
| 3 | Vision 卡片 | 输入框留空；卡片 + 快捷按钮可见 |
| 4 | 复盘意图 | 表达「记错题 / 复盘卷子 / 看看错哪并保存」等**语义** → Agent 调 `classify_photo`，attempt 有 `photo_auto` |
| 5 | 讲解意图 | 「讲讲错的 / 我不会」→ 讲解为主，不整页 classify；可问是否记学情 |
| 6 | 入库 vs 口播 | **入库**（classify_photo）以 vision `is_correct` 为准；**口播**可验算纠错，避免孩子做对了仍被说错；有争议时建议家长确认 |

## 4. 实现清单

- [x] `perception/vision_understand.py`
- [x] `perception/vision_session.py`
- [x] `student_chat.py`：`/api/vision/understand`，chat 传 `vision_id`
- [x] `hermes_bridge.ask(env_extra=...)`
- [x] `pre_llm_student_context_hook` 注入 vision
- [x] `student_chat.html`：Vision 卡片 + 快捷按钮

## 5. 结果（验证后回填）

- 结论：**✅ 通过**（2026-06-23 关闭）
- 证据：
  - `vis-20260623-094116`：24 题 graded_homework，items 含 `is_correct`
  - Vision 卡片 + 输入框留空；Network 仅 `understand` + `chat`（标准 1–3）
  - 「帮我把错题记进学情」→ 17 条 `photo_auto`（09:42，`classify_photo` 整页）✅（标准 4）
  - 「这道我不会」→ 单题讲解，无整页 classify ✅（标准 5）
  - 多轮对话后 `vision_id` 仍随请求（前端 pendingVision 持久化修复）
- **设计取舍（标准 6）**：入库按 vision/批改；口播允许验算——若孩子实际做对、与批改/VLM 不一致，可温和纠正并建议家长确认，避免「做对了还被说错」。
- 真人验证：见 [切片12-执行手册](./切片12-执行手册.md)

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-23 | 初稿 + 实现 |
| 2026-06-23 | 关闭：标准 6 调整为入库/口播分层；vision 多轮保留修复 |

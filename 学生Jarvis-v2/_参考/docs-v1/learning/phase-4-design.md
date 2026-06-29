# 阶段 4 — 推题闭环 · 详细设计

> **状态**：已实现  
> **依赖**：阶段 3 `GapMap` + 种子/SQLite 题库  
> **不含**：Hermes 集成（阶段 5）

---

## 1. 业务目标

- 按 **gap 优先级** 生成 `push_queue.json`，`fetch` 拉取下一包 3～5 题。
- 每次 attempt 后 **重算队列**；gap `mastered` 后降频/不再主推同类题。
- **验收**：关闭一 gap 后，队列头不再以该 gap 题目为主。

---

## 2. 数据模型

### 2.1 `push_queue.json`

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | `"1.0.0"` | |
| `student_id` | string | |
| `updated_at` | datetime | |
| `unit_id` | string | |
| `items` | `PushQueueItem[]` | 有序，index 0 为队头 |
| `batch_size_min` | int | 默认 3 |
| `batch_size_max` | int | 默认 5 |

### 2.2 `PushQueueItem`

| 字段 | 说明 |
|------|------|
| `question_id` | 题目 id |
| `gap_id` | 关联 gap；`unit_practice` 时为 null |
| `knowledge_point_id` | |
| `priority` | 0 最高 |
| `reason` | `gap_remediation` \| `unit_practice` |

### 2.3 SQLite 题库

- 路径：`agent_platform/learning/question_bank/questions.db`（配置 `question_bank.sqlite_path`）
- CLI `bank import` 从 seed JSON 导入
- `QuestionBankService` 优先读 SQLite，无库则回退 JSON

---

## 3. 排队算法（v1）

1. 取 `active` / `improving` gaps，按阶段 3 优先级排序（最多 3 个）。
2. 对每个 gap：在题库中找 `knowledge_point_id` 匹配且 `default_error_code == gap.error_code` 的题；无则放宽为仅 kp 匹配。
3. 排除近 **5** 次 **答对** 的题目（错题仍推，便于补救）；每 gap 最多取 4 题，总队列 ≤ 10。
4. 无 eligible gap → `unit_practice` 填充单元题。
5. 写 `push_queue.json`，同步 `context.focus.queue_head_question_ids`（前 5 id）。

---

## 4. API

| 服务 | 方法 | 说明 |
|------|------|------|
| `PushEngineService` | `rebuild(student_id)` | 重算并持久化 |
| | `peek(student_id, limit=5)` | 看队头 |
| | `fetch(student_id, count=3)` | 取下一包 `Question` |
| `QuestionBankService` | `import_seed_to_sqlite()` | 种子导入 |

### CLI

| 命令 | 说明 |
|------|------|
| `push peek STUDENT_ID` | |
| `push fetch STUDENT_ID [--count N]` | |
| `push rebuild STUDENT_ID` | 手动重算 |
| `bank import` | JSON → SQLite |

---

## 5. 测试方案

| ID | 用例 |
|----|------|
| P-1 | 有 active gap → queue 题属于对应 kp/error_code |
| P-2 | gap mastered → 队列不再以该 gap 为主 |
| P-3 | fetch 返回 3～5 题 |
| P-4 | rebuild 更新 focus.queue_head_question_ids |

集成 `accept_learning_phase4.py`：错题 → peek → fetch → 再答 → 队列变化。

---

## 6. 文件清单

```text
agent_platform/learning/push_engine.py
agent_platform/learning/sqlite_store.py
agent_platform/learning/accept_learning_phase4.py
agent_platform/tests/test_push_engine.py
```

# 阶段 2 — 练习提交与判定 · 详细设计

> **状态**：已实现  
> **依赖**：阶段 1 `StudentContextService`  
> **不含**：Gap 聚合、推题队列（阶段 3/4）

---

## 1. 业务目标

- 学生对**种子题库**提交答案 → 返回 **对错 + 解析 + attempt_id**。
- 每次提交更新 `context.session_stats`：`attempts_today`、`correct_rate_7d`、`last_activity_at`。
- 错题写入 `error_code` 占位（来自题目元数据），供阶段 3 Gap 使用。

---

## 2. 数据模型

### 2.1 `attempts/{attempt_id}.json`

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | `"1.0.0"` | |
| `attempt_id` | string | `att-YYYYMMDD-HHMMSS-{hex6}` |
| `student_id` | string | |
| `question_id` | string | |
| `unit_id` | string | 冗余，便于查询 |
| `submitted_at` | datetime UTC | |
| `answer_raw` | string | 学生原始答案 |
| `answer_normalized` | string | 规范化后 |
| `correct` | bool | |
| `expected_answer` | string | 展示用 |
| `explanation` | string | 题目解析 |
| `error_code` | string \| null | 错时有值，Phase 3 taxonomy |
| `knowledge_point_id` | string | |
| `trace_id` | string | |

### 2.2 种子题库 `question_bank/seed_questions.json`

| 字段 | 说明 |
|------|------|
| `question_id` | 如 `q-fe-001` |
| `unit_id` | 与 curriculum 对齐 |
| `knowledge_point_id` | |
| `stem` | 题干 |
| `answer_type` | `exact` \| `numeric` |
| `expected_answer` | |
| `numeric_tolerance` | 可选，默认配置 |
| `explanation` | |
| `default_error_code` | 错因占位 |

---

## 3. 接口清单

### QuestionBankService

| 方法 | 说明 |
|------|------|
| `list_questions(unit_id=None)` | 列题 |
| `get(question_id)` | 取题，不存在 KeyError |

### Grader

| 方法 | 说明 |
|------|------|
| `grade(question, answer_raw)` → `GradeResult` | exact 去空白比；numeric 容差 |

### AttemptService

| 方法 | 说明 |
|------|------|
| `submit(student_id, question_id, answer)` → `AttemptSubmitResult` | 判题、落盘、刷新 stats |
| `list(student_id, limit=50)` | 按时间倒序 |
| `get(student_id, attempt_id)` | |

### CLI 扩展

| 命令 | 说明 |
|------|------|
| `question list [--unit]` | |
| `question show QUESTION_ID` | |
| `attempt submit STUDENT_ID QUESTION_ID ANSWER` | |
| `attempt list STUDENT_ID` | |

---

## 4. session_stats 计算规则

| 指标 | 规则 |
|------|------|
| `attempts_today` | `submitted_at` 与当前 UTC **同日**的 attempt 数 |
| `correct_rate_7d` | 过去 7×24h 内 `correct=true` / 总数（无 attempt 则 null） |
| `last_activity_at` | 最近一次 `submitted_at` |

---

## 5. 测试方案

### 单元测试 `test_grader.py`

| ID | 用例 |
|----|------|
| G-1 | exact 匹配（忽略首尾空白） |
| G-2 | exact 不匹配 |
| G-3 | numeric 容差内 |
| G-4 | numeric 容差外 |

### 单元测试 `test_attempt.py`

| ID | 用例 |
|----|------|
| A-1 | submit 正确 → correct=true, error_code=null |
| A-2 | submit 错误 → error_code 来自题目 |
| A-3 | session_stats.attempts_today 递增 |
| A-4 | 5 次混合 → correct_rate_7d 手算一致 |
| A-5 | 无 context 时 FileNotFoundError |

### 集成 `accept_learning_phase2.py`

- init 学生 → 连对 3 题 → rate=1.0 → 错 1 题 → rate=0.75  
- CLI attempt submit 返回 JSON 含 `correct`

---

## 6. 文件清单

```text
agent_platform/learning/grader.py
agent_platform/learning/question_bank.py
agent_platform/learning/attempt.py
agent_platform/learning/question_bank/seed_questions.json
agent_platform/learning/accept_learning_phase2.py
agent_platform/tests/test_grader.py
agent_platform/tests/test_attempt.py
```

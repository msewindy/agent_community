# 阶段 6 — 方法辅导与伴随主动 · 详细设计

> **状态**：已实现  
> **依赖**：阶段 4 推题 + 阶段 5 Hermes  
> **不含**：C7 skill 晋升（阶段 7）

---

## 1. 业务目标

- **`study_plan_generate`**：基于 Top gap 生成 20～30 分钟微计划，写入 `plans/{plan_id}.json`，更新 `focus.active_plan_id`。
- **静态 skill 4 条**：`remediation/concept_v1`、`procedure_checklist`、`socratic_hint_flow`、`exam_crunch_plan`。
- **Learning 主动事件**：练后小结、gap 复发（`wrong_7d >= threshold`）、考前提醒（`exam_at` 3 天内）。
- **DND**：`context.flags.do_not_disturb=true` 时事件仍落盘但 `delivered=false`。

---

## 2. 数据模型

### 2.1 `plans/{plan_id}.json`

| 字段 | 说明 |
|------|------|
| `plan_id` | `plan-YYYYMMDD-HHMMSS-{hex6}` |
| `duration_min` | 20～30 |
| `gap_ids` | 关联 gap |
| `steps` | 含 `skill_id`、时长、指引 |
| `skill_ids` | 使用的 remediation skill |

### 2.2 `learning_proactive.jsonl`

每行一条 `LearningProactiveMessage`：`attempt_summary` / `gap_recurrence` / `exam_prep`。

---

## 3. API

| 服务 | 方法 |
|------|------|
| `StudyPlanService` | `generate(student_id)` |
| `LearningProactiveService` | `on_attempt(...)`、`list(student_id)`、`check_exam_prep(student_id)` |
| CLI | `plan generate`、`proactive list` |
| Hermes | `study_plan_generate` |

---

## 4. 验收

- attempt 后 `learning_proactive.jsonl` 含 `attempt_summary` 且 `delivered=true`
- 同错因 `wrong_7d=3` → `gap_recurrence`
- DND 开启 → `delivered=false`
- `study_plan_generate` → `active_plan_id` 更新

---

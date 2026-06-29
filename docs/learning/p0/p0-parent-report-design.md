# P0 — 家长周报告 · 详细设计

> **状态**：已实现（v1）  
> **代码**：`agent_platform/learning/parent_report.py` · `dimension_model.py`  
> **受众**：家长（首期唯一报告对象）

---

## 1. 业务目标

- 每周（可配置天数）汇总孩子 **练习量、正确率、漏洞、维度诊断、行为提示、下一步建议**。
- 报告 **只陈述有 attempt/gap 证据** 的内容；无数据时给出鼓励性默认文案。
- 支持 CLI 输出 JSON 与 Web 面板展示。

---

## 2. 数据来源

| 区块 | 来源 |
|------|------|
| `summary` | `StudentContext` + `LearningKpiService` |
| `knowledge_highlights` | `GapMap`（mastered / active） |
| `dimension_scores` | `DimensionModelService` + attempts |
| `behavior_notes` | 维度 `carelessness` / `reading_care` 信号 |
| `next_steps` | Top active gap + top dimension |
| `evidence` | active gap 的 `evidence_attempt_ids` |

---

## 3. 数据模型 — `ParentWeeklyReport`

| 字段 | 说明 |
|------|------|
| `student_id` | 学生 id |
| `period_days` | 默认 7（yaml `parent_report.default_period_days`） |
| `grade` / `subject` / `unit_title` | 来自 context |
| `attempts_total` | 周期内答题次数 |
| `correct_rate` | 0～1，无数据为 null |
| `dimension_scores[]` | `DimensionScore` |
| `evidence[]` | `{label, gap_id, attempt_id}` |

**持久化**：`student_data/{id}/parent_reports/parent-weekly-{YYYYMMDD}.json`

---

## 4. 接口清单

### ParentReportService

| 方法 | 说明 |
|------|------|
| `build_weekly_report(student_id, period_days?)` | 聚合生成 |
| `save_report(report)` | 写入 parent_reports 目录 |

### CLI

```bash
cli_student parent-report STUDENT_ID [--days 7] [--save]
```

### Web API

见 [p0-web-panel-design.md](./p0-web-panel-design.md)

---

## 5. 维度模型（v1）

配置于 `student_learning.yaml` → `learning_dimensions`：

| id | 标题 | 信号 |
|----|------|------|
| `basic_knowledge` | 基础知识 | CALCULATION_ERROR, PROCEDURE_ERROR |
| `logic_reasoning` | 逻辑推理 | READING_ERROR, WORD_ORDER_ERROR |
| `carelessness` | 粗心 | CALCULATION_ERROR + behavior 粗心 |
| `reading_care` | 审题 | READING_ERROR + behavior 审题 |

`score = min(1, hits / max(wrong_count, 1))`，供家长看 **相对强弱**，非正式测评分数。

---

## 6. 文案原则

- **面向家长**：说明「正在加强 / 已掌握」，避免专业 gap_id 外露（Web 层可隐藏 id）。
- **有证据才断言**：与 AnswerGate 一致，报告内 gap 来自 gap_map 重算结果。
- P0 不推送邮件/微信，仅 **Web + JSON 文件**。

---

## 7. 测试与验收

| 项 | 说明 |
|----|------|
| `accept_learning_p0_smoke` | 6+ attempts → 报告非空 + save |
| CLI `--save` | `_saved_path` 存在 |
| Web GET `/api/students/{id}/parent-report` | 200 + attempts_total |

---

## 8. 后续（P1）

- 多孩切换、对比上周趋势
- 导出 PDF / 分享链接
- 教师端报告（第二受众）

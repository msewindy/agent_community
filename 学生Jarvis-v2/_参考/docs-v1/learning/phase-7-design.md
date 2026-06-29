# 阶段 7 — 进化与试点整包 · 详细设计

> **状态**：已实现  
> **依赖**：阶段 1～6 + C7 `EvolutionStore`  
> **验收**：`accept_learning_full.py` 串联 phase 1～7

---

## 1. 业务目标

- **Learning → C7**：gap `mastered` 或 `wrong_7d` 下降 → 晋升个人 remediation skill  
- **KPI 报告**：90 天窗口正确率、复错率、推题队列完成率（CLI）  
- **种子整包校验**：taxonomy / 题库 / remediation skills 数量  
- **全链路验收**：`accept_learning_full.py`

---

## 2. 进化桥接

| 触发 | 动作 |
|------|------|
| gap `status=mastered` | 写入 `student_data/{id}/evolution/skills/` |
| `wrong_7d` 从 ≥3 下降 | 提升 skill `confidence`，未存在则创建 |

Skill 命名：`student/{student_id}/remediation-{error_code}`

---

## 3. KPI 指标（v1）

| 指标 | 计算 |
|------|------|
| `correct_rate` | 窗口内 correct / attempts |
| `re_error_rate` | 错题中 error_code 7 日内重复的占比 |
| `queue_completion_rate` | 队头题目中有至少一次答对的比例 |
| `gaps_mastered` | gap_map 中 mastered 数量 |

---

## 4. CLI

| 命令 | 说明 |
|------|------|
| `kpi report STUDENT_ID [--days 90]` | JSON 报告 |
| `seed verify` | 种子整包检查 |
| `accept_learning_full.py` | 串联 phase 1～7 |

---

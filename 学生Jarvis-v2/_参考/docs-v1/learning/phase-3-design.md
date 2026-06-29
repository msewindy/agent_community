# 阶段 3 — 漏洞地图 · 详细设计

> **状态**：已实现  
> **依赖**：阶段 2 `AttemptService`、`error_code`  
> **不含**：推题队列（阶段 4）

---

## 1. 业务目标

- 错题按 `student_learning.yaml` 中 **error_taxonomy** 归入 gap。
- 维护 `student_data/{id}/gap_map.json`（架构附录 B）。
- 每次 `attempt submit` 后 **重算 gap_map** 并写回 `context.focus.top_gap_ids`（最多 3 条）。
- **验收**：同一错因错 3 次 → `wrong_7d=3`；同知识点连对 3 次 → `mastered`。

---

## 2. 数据模型

### 2.1 `gap_map.json`

见 [学生Jarvis-v1-架构图.md](../学生Jarvis-v1-架构图.md) 附录 B。

### 2.2 Gap 主键

`gap_id = "gap-" + error_code.lower().replace("_", "-")`  
例：`MISS_MULTIPLY_AFTER_DENOM` → `gap-miss-multiply-after-denom`

### 2.3 状态机（v1 实现）

| 状态 | 条件 |
|------|------|
| `active` | 近 7 日有错，或 streak 未达标 |
| `improving` | `streak_correct > 0` 且 `wrong_7d == 0` |
| `mastered` | `streak_correct >= required_streak` |
| `dormant` | v1 暂不自动写入 |

**连对计数**：答对时，对该题 `knowledge_point_id` 下所有非 `mastered` 的 gap 递增 `streak_correct`。  
**错题**：重置该 `error_code` 对应 gap 的 streak，状态回 `active`。

---

## 3. 接口清单

### TaxonomyService

| 方法 | 说明 |
|------|------|
| `lookup(error_code)` | 标题、默认知识点 |
| `gap_id_for(error_code)` | 稳定 gap_id |
| `version` | taxonomy 版本 |

### GapMapService

| 方法 | 说明 |
|------|------|
| `get(student_id)` | 读 gap_map（无文件则空 gaps） |
| `query(student_id, limit=10)` | 按优先级排序（active/improving，wrong_7d↓） |
| `get_gap(student_id, gap_id)` | 单条 |

### GapMapUpdater

| 方法 | 说明 |
|------|------|
| `rebuild(student_id, attempts, unit_id)` | 自 attempts 全量重算 |
| `apply_after_attempt(...)` | submit 管道钩子 |

### CLI

| 命令 | 说明 |
|------|------|
| `gap list STUDENT_ID` | JSON 数组，无 attempt 时 `[]` |
| `gap show STUDENT_ID GAP_ID` | 单条 gap |

---

## 4. 测试方案

### 单测 `test_taxonomy.py` / `test_gap_map.py`

| ID | 用例 |
|----|------|
| T-1 | taxonomy lookup 已知 error_code |
| T-2 | 未知 error_code → KeyError |
| G-1 | 同错因错 3 次 → wrong_7d=3 |
| G-2 | 同 kp 连对 3 次 → mastered |
| G-3 | 重算后 context.focus.top_gap_ids 更新 |
| G-4 | 无 attempt → gaps 空 |

### 集成 `accept_learning_phase3.py`

- init → 错 3 次 → gap list 含 wrong_7d=3  
- 再连对 3 次 → status=mastered，top_gap_ids 不含该 gap  
- 无 attempt 学生 gap list 为 `[]`

---

## 5. 文件清单

```text
agent_platform/learning/taxonomy.py
agent_platform/learning/gap_map.py
agent_platform/learning/accept_learning_phase3.py
agent_platform/tests/test_taxonomy.py
agent_platform/tests/test_gap_map.py
```

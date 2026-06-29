# P0 — 多维度诊断 v1 · 详细设计

> **状态**：已实现（v1）  
> **代码**：`agent_platform/learning/dimension_model.py`  
> **消费方**：`ParentReportService` · 后续个性化推题（P1）

---

## 1. 业务目标

PRD：**多维度个性化**（非固定「逻辑/基础」二分）。P0 用 **配置化维度** 从错题与 gap 统计 **信号强度**，写入家长报告。

---

## 2. 配置模型

`student_learning.yaml` → `learning_dimensions[]`：

```yaml
learning_dimensions:
  - id: basic_knowledge
    title: 基础知识
    signal_error_codes: [CALCULATION_ERROR, PROCEDURE_ERROR]
  - id: logic_reasoning
    title: 逻辑推理
    signal_error_codes: [READING_ERROR, WORD_ORDER_ERROR]
  - id: carelessness
    title: 粗心
    signal_error_codes: [CALCULATION_ERROR]
    behavior_tags: [粗心]
  - id: reading_care
    title: 审题
    signal_error_codes: [READING_ERROR]
    behavior_tags: [审题]
```

**error_taxonomy** 中 `behavior_tags` 与维度 `behavior_tags` 交集时，叠加 gap 的 `wrong_7d`。

---

## 3. 算法（v1）

对每个维度 `D`：

1. `hits = 0`
2. 遍历周期内 **错题** attempts：若 `error_code ∈ D.signal_error_codes` → `hits += 1`
3. 若配置了 `behavior_tags`：遍历 gap_map，匹配 taxonomy 标签 → `hits += gap.stats.wrong_7d`
4. `score = min(1.0, hits / max(len(wrong_attempts), 1))`
5. 按 `score` 降序排列

### DimensionScore

| 字段 | 说明 |
|------|------|
| `dimension_id` | 配置 id |
| `title` | 展示名 |
| `score` | 0～1，保留 2 位小数 |
| `signal_count` | 原始命中次数 |

### top_dimensions(scores, limit=2)

优先返回 `signal_count > 0` 的维度；全无信号则返回前 N 个（避免空报告）。

---

## 4. 接口清单

| 方法 | 说明 |
|------|------|
| `score_from_attempts(attempts, gap_map?)` | 计算全维度 |
| `top_dimensions(scores, limit=2)` | 报告用 Top N |

---

## 5. P0 二年级示例

| 错题模式 | 可能突出维度 |
|----------|--------------|
| 进位/退位算错 | 基础知识 |
| 应用题列式错 | 逻辑推理 / 审题 |
| 纯计算笔误 | 粗心 |

---

## 6. 限制（v1 已知）

- **非IRT/非标准化测评**，仅供家长参考趋势  
- 维度间 error_code 可重叠（如 CALCULATION 同时喂「基础」和「粗心」）  
- 未单独建模「情绪/动力」维度（P1）

---

## 7. 测试

| 用例 | 说明 |
|------|------|
| 全对 attempts | 各维度 signal_count=0 |
| 混合 CARRY + READING 错题 | 对应维度 signal_count>0 |

可经 `parent-report` 集成验证；单测可选 `test_dimension_model.py`。

---

## 8. 后续（P1）

- 维度权重与家长偏好  
- 推题策略读取 `top_dimensions`  
- 与 Wiki 补救技能映射

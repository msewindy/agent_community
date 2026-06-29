# P0 — KP Catalog + 年级边界 · 详细设计

> **状态**：已实现（v1）  
> **代码**：`agent_platform/learning/kp_catalog.py` · `catalog/kp_catalog.json`  
> **依赖**：`student_learning.yaml` · `OnboardingService` · `AttemptService`

---

## 1. 业务目标

- 将 **知识点（KP）与单元** 从 yaml/种子题字符串提升为 **可查询的 Catalog**。
- **年级绑定**：学生 `grade_level` 不得访问高于其年级的 `unit_id`（推题、做题、onboarding）。
- P0 试点覆盖 **二年级 · 数学 + 语文** 各 1 单元。

---

## 2. 数据模型

### 2.1 `kp_catalog.json`

| 字段 | 说明 |
|------|------|
| `schema_version` | 当前 `1.0.0` |
| `school_stage` | `primary` |
| `units[]` | 单元列表 |

**UnitCatalogEntry**

| 字段 | 类型 | 说明 |
|------|------|------|
| `unit_id` | string | 稳定主键，如 `math-g2-add-sub-100` |
| `grade` | int 1～6 | 单元所属年级 |
| `subject` | string | `数学` / `语文` |
| `unit_title` | string | 展示名 |
| `textbook_ref` | string? | 教材版本引用 |
| `knowledge_points[]` | KP 列表 | `knowledge_point_id` + `title` |

### 2.2 P0 试点单元

| unit_id | grade | subject | KP 数 |
|---------|-------|---------|-------|
| `math-g2-add-sub-100` | 2 | 数学 | 4 |
| `chinese-g2-sentence-basic` | 2 | 语文 | 3 |

---

## 3. 接口清单

### KpCatalogService

| 方法 | 说明 |
|------|------|
| `get_unit(unit_id)` | 单元元数据；未知 id → `KeyError` |
| `list_units(grade_level?, subject?)` | 过滤列表 |
| `assert_student_may_access_unit(student_grade, unit_id)` | 越级 → `GradeBoundaryError` |
| `resolve_grade_level(grade_label, explicit?)` | 「二年级」→ `2` |

### 集成点

| 调用方 | 行为 |
|--------|------|
| `OnboardingService.onboard` | 选单元后校验年级 |
| `AttemptService.submit` | `push.enforce_grade_boundary=true` 时校验题目 `unit_id` |
| `verify_seed_package` | catalog 文件存在性 |

---

## 4. 配置

```yaml
kp_catalog:
  path: agent_platform/learning/catalog/kp_catalog.json

push:
  enforce_grade_boundary: true

pilot:
  grade_level: 2
  units:
    math: math-g2-add-sub-100
    chinese: chinese-g2-sentence-basic
```

---

## 5. 错误与边界

| 场景 | 结果 |
|------|------|
| 一年级学生做二年级单元题 | `GradeBoundaryError` / `AttemptService` → `ValueError` |
| catalog 缺 unit | onboarding 前即失败 |
| 超 catalog 的新 unit_id | 需先扩展 catalog + 种子题 |

---

## 6. 测试与验收

| 项 | 命令/脚本 |
|----|-----------|
| 年级边界 | `accept_learning_p0_smoke.py` |
| onboarding 绑定 | `cli_student onboard demo-stu-g2` |
| 越级 submit | `test_attempt.py::test_grade_boundary_blocks_over_grade_unit` |

---

## 7. 后续（P1+）

- KP 与 Wiki 条目双向链接
- 教材 ingest 审核通过后 **写入 catalog**（见 [p0-textbook-ingest-design.md](./p0-textbook-ingest-design.md)）
- 跨学科、跨年级 rollout 配置化

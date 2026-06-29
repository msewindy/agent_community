# 阶段 1 — 学习情境底座 · 详细设计

> **状态**：已实现  
> **范围**：仅 StudentContext + CLI + 测试（不含 Attempt / Gap / Hermes）

---

## 1. Pydantic 模型 ↔ JSON Schema 对照

| JSON Schema（附录 A） | Pydantic 类型 | 说明 |
|----------------------|---------------|------|
| `schema_version` | `Literal["1.0.0"]` | 常量 |
| `student_id` | `str` | 与目录名一致 |
| `updated_at` | `datetime` | UTC，写入时刷新 |
| `curriculum.grade/subject/unit_id/unit_title` | `Curriculum` | 必填 |
| `curriculum.textbook_ref` | `Optional[str]` | |
| `pipeline_stage` | `PipelineStage` enum | 6 值 |
| `focus.top_gap_ids` | `list[str]` max 3 | Phase 1 可 `[]` |
| `focus.queue_head_question_ids` | `list[str]` max 5 | Phase 1 可 `[]` |
| `focus.active_plan_id` | `Optional[str]` | |
| `goal` | `Optional[LearningGoal]` | |
| `session_stats` | `Optional[SessionStats]` | Phase 2 管道写入 |
| `flags` | `ContextFlags` | 默认 false |
| `trace_id` | `Optional[str]` | 每次写入新 trace |

---

## 2. 接口清单

### StudentContextService

| 方法 | 说明 | Phase |
|------|------|-------|
| `get(student_id) -> StudentContext` | 读 context.json | 1 |
| `init(student_id, curriculum, **kwargs) -> StudentContext` | 新建，已存在则 `FileExistsError` | 1 |
| `patch(student_id, patch: StudentContextPatch) -> StudentContext` | 部分更新，刷新 `updated_at`/`trace_id` | 1 |
| `merge_focus(student_id, top_gap_ids, queue_head_question_ids)` | 管道专用，Phase 3/4 | 3 |
| `merge_session_stats(student_id, ...)` | 管道专用 | 2 |
| `to_prompt_block(ctx) -> str` | pre_llm 注入文本 | 1 |
| `exists(student_id) -> bool` | | 1 |

### CLI `cli_student.py`

| 子命令 | 说明 |
|--------|------|
| `init STUDENT_ID --unit UNIT_ID [--grade] [--subject] [--title]` | 初始化 |
| `show STUDENT_ID` | JSON 输出 |
| `set-stage STUDENT_ID STAGE` | 改 pipeline_stage |
| `prompt STUDENT_ID` | 输出 prompt 块 |

### 存储

- 根：`student_data/`（`student_learning.yaml` → `data.root`）
- 路径：`{root}/{student_id}/context.json`
- 写入：临时文件 + `replace` 原子写

---

## 3. 字段写入权（与架构 §附录 A 一致）

| 字段 | Phase 1 写入方 |
|------|----------------|
| `curriculum`, `goal`, `flags`, `pipeline_stage` | CLI / `patch` |
| `focus.*` | 空；Phase 3+ `merge_focus` |
| `session_stats` | Phase 2+ |
| `updated_at`, `trace_id` | Service 统一 |

# P1-B — 知识点审核与 Catalog Diff · 详细设计

> **状态**：已实现（v1）  
> **代码**：`kp_catalog_diff.py` · `kp_ingest_review.py`  
> **依赖**：P1-A `.kp.md` 解析 · `kp_catalog.json`

---

## 1. 目标

- 待审 `parsed_draft` 与 **已入库 catalog** 自动 **diff**
- 生成 **冲突清单** + **审核 checklist（R1～R6）**
- 冲突须通过 **resolve 动作** 处理，而非单点「通过」
- **P1-B 不写 catalog**；`ready_to_approve=true` 后留给 P1-E `approve`

---

## 2. 分层树（与 Web P1-C 共用）

```
学科 → 年级 → 单元 → 知识点
```

CLI：

```bash
PYTHONPATH=. python agent_platform/learning/cli_student.py catalog tree
PYTHONPATH=. python agent_platform/learning/cli_student.py catalog tree --subject 数学 --grade 2
```

---

## 3. Diff 模型

| 类型 | 含义 |
|------|------|
| `new_unit` | catalog 无此 unit_id |
| `update_unit` | unit 已存在，KP 有增/改/缺 |
| `new` / `unchanged` / `title_changed` | KP 级变化 |
| `missing_in_draft` | catalog 有、文档未写（**禁止静默删除**） |

### 冲突 kind

| kind | 说明 | 允许动作 |
|------|------|----------|
| `unit_exists` | 单元已存在 | use_draft / use_catalog / skip |
| `kp_title_mismatch` | 同 id 不同标题 | use_draft / use_catalog |
| `kp_missing_in_draft` | 文档漏掉 catalog KP | use_catalog / use_draft |
| `kp_cross_unit` | kp_id 挂在别的单元 | skip / rename_draft |
| `subject_grade_mismatch` | 首版 scope 提示 | 信息性，不计入 blocking |

---

## 4. 审核 Checklist

| ID | 规则 | 满足方式 |
|----|------|----------|
| R1 | 确认学科/年级 | `review-confirm --flag confirm_subject_grade` |
| R2 | 冲突全部 resolve | `ingest resolve ...` |
| R4 | 每单元 ≥1 KP | 解析期保证 |
| R5 | 不静默删 KP | missing 冲突须 use_catalog 等 |
| R6 | 确认写入 catalog | `review-confirm --flag confirm_write` |

`ready_to_approve = R1∧R2∧R4∧R5∧R6`

---

## 5. CLI

```bash
# 上传
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest submit \
  --type kp-doc --path docs/content/数学-二年级.kp.md

# 看 diff
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest diff JOB_ID

# 审核态（checklist + conflicts）
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest review JOB_ID

# 处理冲突
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest resolve \
  JOB_ID unit:math-g2-add-sub-100 use_draft

PYTHONPATH=. python agent_platform/learning/cli_student.py ingest resolve \
  JOB_ID kp-missing:math-g2-add-sub-100:kp-g2-xxx use_catalog

# R1 / R6 确认
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest review-confirm \
  JOB_ID --flag confirm_subject_grade
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest review-confirm \
  JOB_ID --flag confirm_write
```

---

## 6. Job 扩展字段

| 字段 | 说明 |
|------|------|
| `catalog_diff` | 完整 diff JSON |
| `review_checklist` | R1～R6 状态 |
| `conflict_resolutions` | 每条冲突的处理 |
| `review_flags` | confirm_subject_grade / confirm_write |
| `ready_to_approve` | 是否可进入 P1-E approve |

---

## 7. 测试

```bash
pytest agent_platform/tests/test_kp_catalog_diff.py \
       agent_platform/tests/test_kp_ingest_review.py -q
```

---

## 8. P1-E Approve 入库（已实现）

`ingest approve JOB_ID` 在 `ready_to_approve=true` 时：

1. 按 `conflict_resolutions` + `parsed_draft` 合并 catalog
2. 写入前备份 `kp_catalog.{timestamp}.bak.json`
3. 审计记录 `{data_root}/_kp_catalog_audit/approve-{job_id}-{ts}.json`
4. Job 状态 → `approved`

```bash
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest approve JOB_ID

# 拒绝（不写 catalog）
PYTHONPATH=. python agent_platform/learning/cli_student.py ingest reject JOB_ID --reason "..."
```

| resolution | 行为 |
|------------|------|
| `use_draft` | 用文档侧 unit/KP 覆盖 |
| `use_catalog` | 保留 catalog（含 missing_in_draft 保留旧 KP） |
| `skip` | 跳过该 unit/冲突项 |
| `rename_draft` | 用 `new_knowledge_point_id` 写入新 KP |

验收：

```bash
pytest agent_platform/tests/test_kp_catalog_merge.py \
       agent_platform/tests/test_kp_ingest_review.py -q
python agent_platform/learning/accept_kp_document_ingest.py
```

---

## 9. P1-C Web 审核页（已实现，含端到端提交）

**页面**：`http://127.0.0.1:8770/kp-review`（与家长学情同端口）

**代码**：`agent_platform/api/student_panel.py` · `templates/kp_review.html`

页面流程：**上传/样例提交 → 选 Job → 处理冲突 → R1/R6 → Approve**

### HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/kp-review` | 审核页 HTML |
| GET | `/api/kp/catalog/tree?subject=&grade=` | 已入库 catalog 树 |
| GET | `/api/kp/ingest/samples` | 内置样例列表 |
| POST | `/api/kp/ingest/submit` | **multipart 上传 `.kp.md`** → 创建 job |
| POST | `/api/kp/ingest/submit-sample` | 提交仓库样例（`math-g2` / `chinese-g2`） |
| GET | `/api/kp/ingest/jobs?status=` | ingest job 列表 |
| GET | `/api/kp/ingest/jobs/{id}/review` | checklist + conflicts + diff |
| POST | `/api/kp/ingest/jobs/{id}/resolve` | 处理单条冲突 |
| POST | `/api/kp/ingest/jobs/{id}/review-confirm` | R1 / R6 确认 |
| POST | `/api/kp/ingest/jobs/{id}/approve` | 合并入库 |
| POST | `/api/kp/ingest/jobs/{id}/reject` | 拒绝 |

上传文件保存在 `{data_root}/_kp_uploads/`。

验收：

```bash
pytest agent_platform/tests/test_student_panel_kp_review.py -q
python agent_platform/learning/accept_kp_review_web.py
```

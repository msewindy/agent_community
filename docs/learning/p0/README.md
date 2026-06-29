# P0 详细设计索引

> **试点**：二年级 · 数学 `math-g2-add-sub-100` + 语文 `chinese-g2-sentence-basic` · Web 家长入口  
> **状态**：六份设计 + 代码 v1 已对齐（2026-06-02）

| 文档 | 模块 | 代码 |
|------|------|------|
| [p0-kp-catalog-design.md](./p0-kp-catalog-design.md) | KP Catalog + 年级边界 | `kp_catalog.py` |
| [p0-textbook-ingest-design.md](./p0-textbook-ingest-design.md) | PDF / 拍照 / 文档 ingest | `textbook_ingest.py` |
| [../p1/kp-document-format.md](../p1/kp-document-format.md) | **P1-A** 知识点 `.kp.md` 格式 | 样例见 [../../content/](../../content/) |
| [../p1/kp-review-design.md](../p1/kp-review-design.md) | **P1-B** catalog diff + 审核 checklist | `kp_catalog_diff.py` |
| [p0-parent-report-design.md](./p0-parent-report-design.md) | 家长周报告 | `parent_report.py` |
| [p0-safety-dialog-design.md](./p0-safety-dialog-design.md) | 域外拒答 + 拉回 | `student_safety.py` |
| [p0-dimension-model-design.md](./p0-dimension-model-design.md) | 多维度诊断 v1 | `dimension_model.py` |
| [p0-web-panel-design.md](./p0-web-panel-design.md) | Web 学情/家长面板 | `api/student_panel.py` |

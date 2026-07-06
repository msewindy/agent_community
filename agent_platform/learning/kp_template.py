"""Blank `.kp.md` template for parent upload (P1-A / P1-1)."""

from __future__ import annotations

KP_MD_TEMPLATE = """---
学科: 数学
年级: 3
教材版本: 北师大版·三年级上册
文档说明: 单学科单年级多单元知识点清单（家长可改）
---

# 单元：示例单元标题

unit_id: math-g3-example-unit
教材章节: 第一单元
单元说明: 用一句话说明本单元学什么。

## 知识点

- 示例知识点标题 → kp-g3-example-01
  说明: 可选，给审核人看的补充说明

- 第二个知识点 → kp-g3-example-02
  说明: 知识点编号 kp-* 全局唯一，建议带年级前缀

## 练习题

- 计算：6 + 3 × 4 = ? → q-g3-ex-001
  知识点: kp-g3-example-01
  答案: 18
  题型: exact
  解析: 先算乘法 3×4=12，再算加法 6+12=18。
  错因: PROCEDURE_ERROR
"""

KP_QUESTIONS_ONLY_TEMPLATE = """---
学科: 数学
年级: 3
教材版本: 北师大版·三年级上册
文档说明: 仅补充练习题（单元须已在知识库中）
---

# 单元：混合运算（第一单元）

unit_id: math-g3-mixed-ops
教材章节: 第一单元

## 练习题

- 计算：6 + 3 × 4 = ? → q-g3m-new-001
  知识点: kp-g3-mix-mult-add
  答案: 18
  题型: exact
  解析: 先算乘法 3×4=12，再算加法 6+12=18。
  错因: PROCEDURE_ERROR

- 计算：20 - 3 × 4 = ? → q-g3m-new-002
  知识点: kp-g3-mix-mult-sub
  答案: 8
  解析: 先算 3×4=12，再算 20-12=8。
  错因: PROCEDURE_ERROR
"""

KP_FORMAT_GUIDE_BRIEF = """知识点文档（.kp.md）快速说明

1. 文件命名：{学科}-{年级}.kp.md，例如 数学-三年级.kp.md、英语-三年级.kp.md
2. 文件头必填：学科、年级、教材版本（YAML frontmatter；学科可为 数学 / 语文 / 英语 等）
3. 每个单元一块：# 单元：标题 + unit_id: ...
4. 知识点列表：- 标题 → kp-编号
5. 练习题（可选）：## 练习题 + 题干 → q-编号 + 知识点/答案/解析/错因
6. 英语题错因示例：SPELLING_ERROR、GRAMMAR_ERROR、VOCAB_GAP、EN_READING_ERROR
7. 完整英语样例见 docs/content/英语-三年级.kp.md
8. 上传后打开「知识点入库」或「习题处理」→ 批准入库
9. 知识点下次提问自动生效；练习题写入 SQLite 后可推题

完整格式见 docs/learning/p1/kp-document-format.md
"""

QUESTIONS_FORMAT_GUIDE_BRIEF = """仅练习题文档（.kp.md）快速说明

1. 单元 unit_id 必须已在知识库（先录入知识点，或同一文件含 ## 知识点）
2. 每个单元写 ## 练习题，每题格式：
   - 题干 → q-编号
     知识点: kp-xxx
     答案: ...
     解析: ...
     错因: PROCEDURE_ERROR（须在错因表中）
3. 上传入口：家长端「题库管理」或「知识点入库」
4. 批准后即 merge 入题库，无需重启 8771
"""

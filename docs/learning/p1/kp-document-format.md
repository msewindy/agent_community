# P1-A — 知识点文档格式（`.kp.md`）

> **范围**：单文件 = **单学科 + 单年级 + 多单元**  
> **存储**：教研维护 `.kp.md` → 解析 → 审核 → 写入 `kp_catalog.json`（机器仍用 JSON，人不直接改 catalog）

---

## 1. 模板是否跨学科一致？

**可以，且应当一致。**

| 层级 | 数学 / 语文 | 是否相同 |
|------|-------------|----------|
| 文件头（frontmatter） | 学科、年级、教材版本 | ✅ 相同字段 |
| 单元块 | `# 单元：` + `unit_id` | ✅ 相同 |
| 知识点列表 | `- 标题 → kp_id` | ✅ 相同 |
| 可选说明行 | 单元说明、KP 说明 | ✅ 相同语法（内容因学科而异） |
| 可选扩展行 | 如 `能力标签:` | ⚪ 可选，解析器忽略未知行 |

学科差异体现在 **文字内容** 和 **kp_id 命名**，不体现在文件结构上。

---

## 2. 文件命名

```
{学科}-{年级}.kp.md
```

示例：`数学-二年级.kp.md`、`语文-二年级.kp.md`

---

## 3. 语法规范

### 3.1 文件头（YAML frontmatter，必填）

```yaml
---
学科: 数学          # 必填：数学 | 语文
年级: 2             # 必填：1～6 整数
教材版本: 人教版·二年级上册   # 必填：自由文本
文档说明: 单学科单年级多单元知识点清单   # 可选
---
```

### 3.2 单元块（可重复多个）

```markdown
# 单元：{单元标题}

unit_id: {全局唯一 id，如 math-g2-add-sub-100}
教材章节: {可选，如 第二单元}
单元说明: {可选，一段话}

## 知识点

- {知识点标题} → {knowledge_point_id}
  说明: {可选，给审核人看的补充}
```

**知识点行规则**

- 每条 KP 一行，格式：`- 标题 → kp_id`（箭头两侧可有空格）
- `kp_id` 建议：`kp-{学科缩写}-g{年级}-{slug}`，如 `kp-g2-add-carry`
- 同一文件内 `unit_id`、`kp_id` 均不可重复

### 3.3 练习题块（可选，`## 练习题`）

与 `## 知识点` 同处一个单元块内，可单独出现（仅补题）或与知识点并存：

```markdown
## 练习题

- 计算：6 + 3 × 4 = ? → q-g3m-001
  知识点: kp-g3-mix-mult-add
  答案: 18
  题型: exact
  解析: 先算乘法 3×4=12，再算加法 6+12=18。
  错因: PROCEDURE_ERROR
```

| 子字段 | 必填 | 说明 |
|--------|------|------|
| 题行 `- 题干 → q-id` | ✅ | `q-*` 全局唯一 |
| `知识点:` | ✅ | 须为 catalog 或同文件 draft 中的 `kp_id` |
| `答案:` / `解析:` / `错因:` | ✅ | 错因须在 taxonomy 中 |
| `题型:` | 默认 `exact` | `exact` 或 `numeric` |
| `容差:` | numeric 时建议 | 浮点容差 |

**仅练习题文档**：可省略 `## 知识点`，但 `unit_id` 必须已在 `kp_catalog.json` 中。

### 3.4 解析器将忽略

- Markdown 普通段落（不在单元块结构内）
- 以 `#` 开头但不是 `# 单元：` 的标题（会报 warning）

---

## 4. 与 catalog JSON 的映射

| `.kp.md` | `kp_catalog.json` |
|----------|-------------------|
| frontmatter `学科` | `units[].subject` |
| frontmatter `年级` | `units[].grade` |
| frontmatter `教材版本` | `units[].textbook_ref`（单元未单独写时使用） |
| `# 单元：标题` | `units[].unit_title` |
| `unit_id:` | `units[].unit_id` |
| `- 标题 → kp_id` | `units[].knowledge_points[]` |

---

## 5. 样例文件

| 文件 | 说明 |
|------|------|
| [../../content/数学-二年级.kp.md](../../content/数学-二年级.kp.md) | 参考人教版二上「100以内的加法和减法（二）」 |
| [../../content/语文-二年级.kp.md](../../content/语文-二年级.kp.md) | 参考二上「句子与标点」专项 + 词语搭配单元 |
| [../../content/数学-三年级-完整样例.kp.md](../../content/数学-三年级-完整样例.kp.md) | **家庭 Alpha 完整样例**：KP 说明 + 练习题 + Wiki 同步 |

> 样例内容依据公开教学资料中的 **单元划分与知识点归纳** 整理，用于产品试点，非教材原文。

---

## 6. 常见错误

| 错误 | 后果 |
|------|------|
| 一份文件含数学+语文 | 解析拒绝 |
| 年级与 frontmatter 不一致 | 解析拒绝 |
| 缺少 `unit_id` 或 KP 箭头 | 解析报错，行号提示 |
| 使用 JSON 代替 `.kp.md` | 不走本管道（请转为本格式） |

---

## 7. CLI（P1-A 已实现）

```bash
cd $AGENT_COMMUNITY_ROOT
export PYTHONPATH=.

python agent_platform/learning/cli_student.py ingest submit \
  --type kp-doc --path docs/content/数学-二年级.kp.md

python agent_platform/learning/cli_student.py ingest list
python agent_platform/learning/cli_student.py ingest show ing-YYYYMMDD-HHMMSS-xxxxxx
```

成功时 job 含 `parsed_draft`（完整单元/KP 树）与 `kp_candidates`（扁平列表），状态为 `pending_review`。


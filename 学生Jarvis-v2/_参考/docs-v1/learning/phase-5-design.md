# 阶段 5 — 对话助理集成 · 详细设计

> **状态**：已实现  
> **依赖**：阶段 1–4 learning 模块  
> **不含**：方法辅导 / 主动推送（阶段 6）

---

## 1. 业务目标

- Hermes 插件 **`agent-student`** 暴露学习域工具。
- **`pre_llm_call`** 注入 StudentContext + Top gaps + AnswerGate 规则。
- **AnswerGate**：对掌握/漏洞类断言要求 `gap_id` 或 `attempt_id` 证据，否则降级为引导式话术。
- **验收**：有 context 时 pre_llm 含单元名；无 gap 时 gate 拦截「反复出错」类断言。

---

## 2. Hermes 插件

| 路径 | 说明 |
|------|------|
| `integrations/hermes/agent_student/` | plugin.yaml + register |
| `integrations/hermes/student_tools.py` | handlers + hook |

### 2.1 工具

| 工具 | 说明 |
|------|------|
| `student_context_get` | 读 context + prompt_block |
| `gap_map_query` | Top gaps |
| `attempt_submit` | 提交答案 |
| `push_queue_peek` | 队头预览 |
| `student_answer_gate` | 校验/降级输出 |

### 2.2 Hook

| Hook | 行为 |
|------|------|
| `pre_llm_call` | 注入 `STUDENT_JARVIS_SYSTEM` + CTX + gaps + `ANSWER_GATE_RULES` |

### 2.3 student_id 解析顺序

1. 工具参数 `student_id`  
2. 环境变量 `STUDENT_JARVIS_STUDENT_ID`  
3. `student_learning.yaml` → `hermes.default_student_id`

---

## 3. AnswerGate

检测掌握/漏洞类话术（如「反复」「薄弱」「已掌握」）。  
通过条件：文本含 `gap-*` 或 `att-*`，且（若提到 gap_id）与 `gap_map_query` 数据一致。  
否则返回引导式降级文案。

---

## 4. 测试方案

| ID | 用例 |
|----|------|
| H-1 | pre_llm 注入含 unit_title |
| H-2 | gap_map_query 返回 wrong_7d |
| H-3 | answer_gate 无证据拦截 |
| H-4 | answer_gate 有 gap_id 通过 |
| H-5 | attempt_submit 工具端到端 |

集成：`accept_learning_phase5.py` + `smoke_hermes_student_tools.py`

---

## 5. 安装

```bash
./agent_platform/integrations/hermes/install_plugin.sh
hermes plugins enable agent-student
hermes tools enable agent_student
export STUDENT_JARVIS_STUDENT_ID=demo-stu-01
```

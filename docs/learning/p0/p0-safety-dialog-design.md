# P0 — 域外拒答 + 拉回 · 详细设计

> **状态**：已实现（v1）  
> **代码**：`agent_platform/learning/student_safety.py` · Hermes `student_safety_check` · `pre_llm` hook

---

## 1. 业务目标

PRD 决策：**先拒答再拉回**。当学生提出与学习无关或不适宜的请求时：

1. **不执行** 代写、游戏、恋爱等域外内容  
2. **温和拒答** + **拉回** 当前学科（数学/语文）  
3. 可选继续：练题 / 看家长报告

---

## 2. 检测策略（v1）

**规则匹配**（非 LLM 分类），配置于 yaml：

```yaml
student_safety:
  enabled: true
  redirect_template: "这个我没办法帮你。{empathy}我们继续学{subject}吧，要练几题还是看本周学习报告？"
  off_topic_patterns:
    - 代写
    - 帮我写.*作文
    - 游戏
    - 王者荣耀
    - 谈恋爱
```

| reason_code | 含义 |
|-------------|------|
| `disabled` | 功能关闭，一律放行 |
| `empty` | 空消息，放行 |
| `ok` | 未命中规则 |
| `off_topic` | 命中，需 redirect |

---

## 3. 接口清单

### StudentSafetyService

| 方法 | 说明 |
|------|------|
| `check_user_message(text, subject?)` | → `SafetyCheckResult` |
| `enabled` | 读取 yaml 开关 |

### Hermes

| 入口 | 行为 |
|------|------|
| `student_safety_check` tool | 供 Agent 显式自检用户句 |
| `pre_llm_student_context_hook` | 若 kwargs 含 `user_message` 且 off_topic → 注入拒答指令 |

### SafetyCheckResult

| 字段 | 说明 |
|------|------|
| `allowed` | 是否可继续正常对话 |
| `reason_code` | 见上表 |
| `redirect_message` | 拒答+拉回话术（off_topic 时必填） |

---

## 4. 与 AnswerGate 分工

| 模块 | 职责 |
|------|------|
| **StudentSafety** | 用户 **输入** 域外（代写、游戏…） |
| **AnswerGate** | 助手 **输出** 无 gap/attempt 证据的断言 |

二者可同时生效：域外输入在 pre_llm 阶段即限制；输出仍走 AnswerGate。

---

## 5. 二年级话术要求

- 短句、无恐吓；见 `prompts.py` → `SAFETY_REPLY_RULES`
- `{subject}` 替换为当前学科（如「数学」），勿写「语文或数学」给小朋友听

---

## 6. 测试与验收

| 用例 | 期望 |
|------|------|
| 「帮我代写作文」 | `allowed=false`，含 redirect |
| 「47+38等于多少」 | `allowed=true` |
| pre_llm + user_message 域外 | context 含拒答段 |

```bash
pytest agent_platform/tests/test_student_hermes_tools.py::test_pre_llm_blocks_off_topic -q
python agent_platform/learning/accept_learning_p0_smoke.py
```

PRD：**域外请求 100% 拒答并拉回**（抽检剧本 US-11）。

---

## 7. 后续（P1）

- 可配置白名单（如「我想休息」→ 鼓励而非拒答）
- 敏感级别分级（安全类 vs 纯域外）
- 审计日志 `student_data/{id}/safety_events.jsonl`

# Agent 技术学习路线与实践指南

本文档承接《底座架构详细设计报告》《个人 Agent 定义·能力分层》中的技术选型，整理 **从生成式大模型之上** 系统理解 Agent 的路径；并单独展开第一站：**MCP** 与 **Skill** 的资料与实践入口。

---

## 1. 学习目标边界（建议）

| 深度 | 内容 |
|------|------|
| **不必深挖** | 多模态基座内部结构、训练与微调理论（除非你要做训推一体或端侧极限优化）。 |
| **需要搞懂** | 在模型之上：**工具协议、上下文与记忆、任务编排、治理门控、进化与 Skill** 如何接成可维护系统。 |
| **模型侧保留** | 上下文窗口与成本、多模态消息形态、**结构化输出（JSON/schema）**、何时摘要/裁剪历史。 |

---

## 2. 总体学习地图（与底座分层对齐）

按依赖与性价比，建议优先级如下。

| 优先级 | 主题 | 要回答的设计问题 |
|--------|------|------------------|
| **P0** | 工具与上下文协议（**MCP** + 运行时工具循环） | 工具如何发现、调用、鉴权、审计；与模型上下文如何衔接。 |
| **P1** | 记忆与知识（MemVerse / RAG / LLM Wiki） | 写什么、何时写、如何检索、冲突与生命周期。 |
| **P2** | 任务编排与 Agent 运行时（Hermes / OpenClaw 等） | Task/DAG、重试、人机确认点如何挂在执行路径上。 |
| **P3** | 进化与 **Skill**（Leaper 思路） | 从轨迹到 Skill、版本、灰度、负例验证。 |
| **P4** | 治理（Holomime 思路 + L0–L4） | 规则谁执行、高风险如何不可绕过。 |
| **P5** | 具身与感知（Reachy） | 感知如何事件化、与对话/记忆的分界。 |

---

## 3. 建议节奏（示例：约两周）

| 周次 | 重点 |
|------|------|
| **第 1 周** | 跑通 MCP（Server + Client + 一次真实工具调用）；选一个运行时仓库追 **一条完整 agent loop**；粗读 MemVerse（或等价）的 **写入/检索** API 与数据模型。 |
| **第 2 周** | 搭最小 LLM Wiki 目录 + 一次「问答 → 归档成页」；读 Leaper（或本地 `research_repos/leaper-agent`）**进化主链路**；Holomime 读 **规则如何落地**；Reachy 只看 **事件边界**。 |

---

## 4. 第一站：MCP（Model Context Protocol）

### 4.1 为何先看 MCP

它是当前事实上的 **「模型 ↔ 外部世界」插口标准**：工具发现、多传输方式、生态复用，与《底座架构》中的 **MCP 优先工具总线** 一致。先 MCP，再叠记忆与进化，路径最顺。

### 4.2 权威资料（建议阅读顺序）

1. **协议总览**  
   - [What is MCP?](https://modelcontextprotocol.io/introduction)  
   - 文档索引（便于全文检索）：[modelcontextprotocol.io 文档索引 / llms.txt](https://modelcontextprotocol.io/llms.txt)

2. **概念与架构**  
   - 官方文档中的 **Tools / Resources / Prompts**、传输方式（stdio、HTTP/SSE 等以当前文档为准）。

3. **Python SDK（服务端与客户端）**  
   - 仓库：[modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)  
   - 文档站点（若官方指向更新域名，以仓库 README 为准）：实现 **Server、Client、FastMCP** 等快速写法。

4. **教程（分层练习）**  
   - 社区整理的分级教程入口：[MCP Tutorials - modelcontextprotocol.info](https://modelcontextprotocol.info/docs/tutorials/)（从「概念 → Server → Client」按需选章节）。

5. **客户端生态（你知道会用在哪里即可）**  
   - [Cursor：MCP](https://cursor.com/docs/context/mcp) — 本机开发时常用。  
   - [VS Code Copilot：MCP](https://code.visualstudio.com/docs/copilot/chat/mcp-servers)  
   - 其他客户端列表见 [MCP 官网 Clients](https://modelcontextprotocol.io/clients)。

6. **注册表（找现成 Server）**  
   - [MCP Registry](https://registry.modelcontextprotocol.io/) — 浏览可用 Server，减少从零造轮子。

### 4.3 官方参考实现（最适合练手）

- 仓库：[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)  
- 内含参考 Server（如 **Everything** 测试用、**Filesystem**、**Fetch**、**Git**、**Memory** 等），用于对照协议能力与 SDK 用法。  
- 阅读顺序建议：**README → 选一个最小 Server 的源码目录 → 对照 Python SDK 文档写自己的最小 Tool**。

### 4.4 推荐最小实践（≈ 半天～1 天）

按顺序完成即可视为「MCP 第一站通关」：

1. **读**：Introduction + `llms.txt` 里与 tools/transports 相关的页面（约 1～2 小时）。  
2. **跑**：本地启动官方参考里的 **Everything** 或 **Filesystem**（按该仓库 README），在 Cursor（或你常用的 MCP Client）里 **能看到工具列表并成功调用一次**。  
3. **写**：用 Python SDK 写一个 **极简 MCP Server**：只暴露一个工具（例如 `add(a,b)` 或「读本地某配置文件」），stdio 启动；再用最小 Client 或 Cursor 连接验证 **list_tools → call_tool**。  
4. **记**：用一段话写下：**discovery → invoke → 返回 → 审计点** 在你未来的集成中枢里应落在哪一层。

### 4.5 进阶方向（可选）

- 远程传输（HTTP/SSE）与权限、多租户下的暴露边界。  
- 把 **MemVerse / Reachy** 等专有 API **包成 MCP Server**，与《底座》里「专有接口 MCP 适配」一致。

---

## 5. 第一站（并行）：Skill 指什么、学什么

「Skill」在讨论里容易混用，建议在心里拆成三层：

| 概念 | 含义 | 典型资料与落地 |
|------|------|----------------|
| **MCP Tool** | 对外暴露的 **原子能力**（一次可调用的函数/接口）。 | MCP 官方文档、参考 `servers` 仓库。 |
| **进化 Skill（Leaper / 底座文档）** | 从任务轨迹 **提炼** 的可复用流程：触发条件、步骤、版本、灰度、**反例**。 | 本地 `research_repos/leaper-agent`（若已克隆）；重点文件可参考《开源项目下载与分析报告》中的 **`agent/leaper_evolution.py`（L0–L5）**。 |
| **IDE / Cursor Skill** | 编辑器侧 **SKILL.md** 类工作流（与进化引擎不是同一套实现，但「可复用规程」思想相通）。 | Cursor 文档中的 Skills / Rules（按需）。 |

### 5.1 与「工具调用」相关的通用资料（补模型侧接口）

这些帮助你理解「为何要有 schema、为何要有确认链」，与《底座》里 **L0–L4** 呼应：

- OpenAI：**Function calling / Tools**（以当前官方文档为准）。  
- Anthropic：**Tool use**（以当前官方文档为准）。  
- 不必通读全文，重点看：**消息结构、tool 定义、多轮 tool 循环**。

### 5.2 进化 Skill 的实践建议（与 MCP 的关系）

1. 先用 MCP 把 **单步工具** 做稳（第一节通关）。  
2. 再在 Leaper（或自研最小原型）里实现：**任务结束 → 写轨迹 → 生成一条「Skill 草稿」（JSON/YAML）→ 下次 planning 能引用该 Skill**。  
3. 给每条 Skill 加 **1～3 个反例场景**（与《底座》负向验证一致），在灰度里看误触发。

### 5.3 本仓库内可本地对照的路径

- **Leaper**：`research_repos/leaper-agent/`（若未克隆，可先完成开源报告中的下载步骤）。  
- **Reachy「skills」目录**（机器人场景下的规程文档，与进化 Skill 不同，但可借鉴「场景化 SOP」写法）：`research_repos/reachy_mini/skills/`。

### 5.4 Skill 更详细的资料（相对 MCP 的补充）

先把「Skill」拆清楚，再选读物；否则容易把 **工具调用 / Hermes 规程包 / 进化引擎里的 Skill** 混在一起。

#### A. 三层含义（对照阅读）

| 层级 | 是什么 | 你要读的深度 |
|------|--------|----------------|
| **① 规程型 Skill（Hermes / Leaper 生态）** | 一组 **`SKILL.md` + 可选脚本**：被加载后相当于「系统 prompt + 操作手册」，可版本、可安装（`hermes skills install …`）。 | **官方文档 + 仓库里 bundled skills 的目录结构**。 |
| **② 进化 Skill（Leaper `leaper_evolution`）** | 从对话/轨迹里 **自动生成与治理** 的知识片段与技能描述（L0–L5：召回→提炼→合成→治理→用户建模→验证）。 | **README「六层记忆引擎」+ 源码 `agent/leaper_evolution.py` 按函数顺藤摸瓜**。 |
| **③ IDE / 产品型 Skill** | 如 **Cursor** 的 `SKILL.md` 工作流，与 ① 思想类似，但跑在编辑器产品里。 | **Cursor 文档** + 你本机 `.cursor/skills` 里现成结构。 |

与 **MCP** 的关系：MCP 解决 **「可调用的外部能力怎么接」**；①② 解决 **「规程从哪来、怎么越用越准」** —— 二者常组合使用（例如 Hermes 生态里也有 `mcp-*` 类 skills）。

#### B. 官方与一手源码（建议顺序）

1. **Leaper Agent（自学习 + 六层进化，与《底座》Leaper 条最贴）**  
   - 仓库：[github.com/Deepleaper/leaper-agent](https://github.com/Deepleaper/leaper-agent)  
   - 先读根目录 **README** 的「六层记忆引擎」「4Gate 门控」—— 这是产品化说明。  
   - 再读 **`agent/leaper_evolution.py` 文件头 docstring**（L0–L5 与实现一一对应），然后按 **L1 `experience_extract` → L2 `skill_generate` → L3 `skill_evolve` → L5 `validate`** 跟进函数（其余为辅助）。  
   - 分发包说明：[PyPI：leaper-agent](https://pypi.org/project/leaper-agent/)（版本与 CLI 以页面为准）。  

2. **Hermes Agent（上游：规程 Skill、CLI、`skills/` 体系）**  
   - 仓库：[github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)（仓库名大小写以跳转为准）  
   - 文档站：[hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs) — 重点看 **User Guide → Skills**（bundled / optional、如何安装与触发）。  
   - 想一次看清「官方怎么解释 Hermes 自己」：仓库内 [skills/.../hermes-agent/SKILL.md](https://github.com/NousResearch/hermes-agent/blob/main/skills/autonomous-ai-agents/hermes-agent/SKILL.md)（长但信息密度高，可搜关键词分段读）。  

3. **自进化 / Hermes 变体（社区深读，非必须）**  
   - 如 [adrianlerer/hermes-agent-self-evolution](https://github.com/adrianlerer/hermes-agent-self-evolution) 等 fork，适合对比「在 Hermes 上加一层自进化」的剪彩点。  
   - 解读向文章（非官方）：如 dev.to 上 *Hermes Agent* 长文，适合建立整体心智图，**实现细节仍以仓库为准**。  

4. **Skill 市场与目录（看生态长什么样）**  
   - 例：[Lethe044/hermes-skill-marketplace](https://github.com/Lethe044/hermes-skill-marketplace) — 看 **别人如何打包、分类、发布规程型 Skill**（与自研目录规范可对标）。  

5. **IDE 侧（你已经在用 Cursor 时）**  
   - [Cursor 文档里与 Agent / Rules / Skills 相关章节](https://cursor.com/docs)（路径以官网最新导航为准）— 关注 **SKILL.md 元数据、何时注入上下文**，与 ① 对照。  

#### C. 研究向（optional，讲「从环境学习技能」的学术叙事）

若你想把 **「Skill = 可复用策略/程序」** 放在研究史里理解，可补读（与具体工程实现不是一一对应）：

- **Voyager**（Minecraft 里通过代码/技能库不断扩展）— 搜 `Voyager Minecraft GitHub` 读论文 + 仓库 README。  
- **Generative Agents**（记忆与日程仿真）— 理解「记忆→行为」的研究范式即可。

#### D. 实践路径（比再找文章更有效）

1. 本地已有 **`research_repos/leaper-agent`**：打开 **`agent/leaper_evolution.py`**，对照 README 表格 **手写一张数据流草图**（从一轮对话结束到写入 brain）。  
2. 打开 **`skills/`**（或 `bundled-skills` 等价路径）里 **任意一个简单 SKILL.md**，看 **frontmatter + 正文如何约束 Agent**，再对照底座报告里的 **Skill JSON** 设计差异（规程 vs 结构化存储）。  
3. 若你希望规程可被 Hermes CLI 加载：按 Hermes 文档 **安装 1 个 bundled skill**，在日志里观察 **skill 何时被 attach**。  

---

## 6. 与项目文档的交叉引用

- 架构与分层：[底座架构详细设计报告.md](./底座架构详细设计报告.md)  
- 产品与能力模块：[个人Agent定义_能力分层_可行方案.md](./个人Agent定义_能力分层_可行方案.md)  
- 各开源仓库说明：[开源项目下载与分析报告.md](./开源项目下载与分析报告.md)

---

## 7. 文档维护

- **版本**：v1.1（补充「Skill 更详细资料」§5.4；与底座 v0.2 叙事一致；外部链接若变更，以各官网 / GitHub 为准）。  
- **更新**：新增「第二站：记忆与 Wiki」时可复制本文结构，单独成篇以免单文件过长。

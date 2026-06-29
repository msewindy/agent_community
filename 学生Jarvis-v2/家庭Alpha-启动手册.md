# 家庭 Alpha · 启动手册（一页纸）

> **版本**：学生 Jarvis v2 · 家庭 Alpha · 三年级学习版（2026-Q3）
> **学生**：`g2-stu-01`（升三年级，历史学情保留）
> **主攻单元**：数学 · `math-g3-mixed-ops`（混合运算）
> **状态**：Phase 0–3 已完成，可直接试用

---

## 1. 启动前 30 秒检查

| 项 | 要求 |
|----|------|
| 运行环境 | WSL2 Ubuntu；仓库 `/mnt/c/Users/Administrator/Desktop/agent_community` |
| API Key | `~/.hermes/.env` 含 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` |
| Hermes | `hermes doctor` → `✓ agent_student` |
| 浏览器 | Chrome / Edge（语音需 HTTPS 或 localhost） |

```bash
cd /mnt/c/Users/Administrator/Desktop/agent_community
export PATH=$HOME/.hermes/hermes-agent/venv/bin:$PATH
PY=$HOME/.hermes/hermes-agent/venv/bin/python

hermes doctor
```

---

## 2. 启动服务

**孩子聊天**（必开）：

```bash
$PY -m uvicorn agent_platform.api.student_chat:app --host 0.0.0.0 --port 8771
```

**家长学情**（按需）：

```bash
$PY -m uvicorn agent_platform.api.student_panel:app --host 0.0.0.0 --port 8770
```

| 角色 | 地址 |
|------|------|
| 孩子（本机） | http://127.0.0.1:8771/ |
| 孩子（平板/手机，同 WiFi） | http://\<电脑局域网 IP\>:8771/ |
| 家长学情 | http://127.0.0.1:8770/ |

> 试用期间保持 8771 常开；关电脑即不能聊。

---

## 3. 第一次陪跑（约 30 分钟）

按顺序走一遍，确认五环节都能用：

| # | 环节 | 孩子可以说 | 预期 |
|---|------|------------|------|
| 1 | **教** | 「今天我们学乘加混合运算，你先讲讲」 | **分步讲解**，不出 52−18 等无关题 |
| 2 | **练** | 「再给我 3 道题」 | 出 **G3 混合运算**题（`questions_suggest`） |
| 3 | **查** | 孩子口头/打字作答 | Jarvis 判对错并反馈 |
| 4 | **补弱** | 「退位减法我还不会，再练几题」 | 应推到 G2 退位题（`52−18` 等） |
| 5 | **拍** | 📷 拍批改卷 → 点「帮我把错题记进学情」 | Vision 卡片 → 记入学情或进 inbox |

家长开 8770：看 KP 掌握 + 待归类队列。

---

## 4. 日常话术（养成习惯即可）

```
学新课：「小贾，今天我们学 XXX，你先讲讲。」
练题：  「再给我几道题。」 / 「来 3 道类似的。」
求助：  「这道我不会，教教我。」
记错题：拍完 → 点橙色按钮，或说「帮我把错题记进学情」
不想做： 「今天不想做题了。」 → 观察是否先共情、不硬推题
```

---

## 5. 家长每周 5 分钟

| 动作 | 频率 |
|------|------|
| 8770 刷新学情 + 处理 inbox（挂 KP / 忽略） | 每周 1 次 |
| 记录反馈（见下表） | 每周 1 次 |

**反馈表（打勾即可）**

| 问题 | 是 / 否 / 备注 |
|------|----------------|
| 孩子愿意主动用吗？ | |
| 哪一步最容易卡住？ | |
| 等回复是否太久（>30s）？ | |
| 讲题是否清楚、有无超纲？ | |
| 推题是否对口（G3 新知 / G2 补弱）？ | |
| 拍照归类是否合理？ | |

---

## 6. 快速核对（CLI，可选）

```bash
$PY -m agent_platform.learning.cli_student context show g2-stu-01
$PY -m agent_platform.learning.cli_student push peek g2-stu-01
$PY -m agent_platform.learning.cli_student attempt list g2-stu-01 --limit 5
$PY -m agent_platform.learning.cli_student gap list g2-stu-01
```

---

## 7. 本版承诺 / 不承诺

| ✅ 承诺 | ❌ 不承诺 |
|---------|-----------|
| 教、练、查、家长学情、按薄弱再练（已录入单元内） | 整册三年级全覆盖 |
| G3 新知 + G2 历史 gap 可补（Phase 3 已放宽） | 公网部署、多孩子切换 UI |
| 拍照理解 + 记学情 / 讲解 | 流式秒回、孩子端学情仪表盘 |

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| 等半分钟才有回复 | 正常；告诉孩子「小贾要想一会儿」 |
| 平板打不开 8771 | 用电脑局域网 IP，不要用 127.0.0.1；检查防火墙 |
| 推题还是 G2 退位 | 说「来几道**混合运算**题」；或「**退位**再练」走补弱 |
| 拍照全进 inbox | 家长 8770 手动挂 KP；或 catalog 缺对应 KP |
| 改了配置不生效 | 重启 8771 |

---

## 9. 内容滚动扩展

学完第一单元后：

1. 编写下一 unit 的 `.kp.md` → `/kp-review` approve
2. 准备 seed JSON → `cli_student bank import`
3. patch `g2-stu-01` 的 `unit_id` → `push rebuild`

---

**给孩子的三句话**：① 小贾要想一下才回答，别着急。② 不会的题可以打字、说话，或拍照片。③ 拍完后点橙色按钮，或者说「教教我」。

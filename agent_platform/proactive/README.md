# 主动行为层（M5 / US-5）

| 里程碑 | 状态 |
|--------|------|
| D1 配置 + 引擎骨架 | ✅ |
| D2 Hermes + 记忆加固 | ✅ |
| D3 工时意图 | ✅ |
| D4 Voice 挂钩 | ✅ |
| D5 统一验收 | ✅ |
| D6–D10 US-5 正式验收 | ✅ |

```bash
PYTHONPATH=. python agent_platform/proactive/smoke_proactive_d1.py
PYTHONPATH=. python agent_platform/proactive/smoke_proactive_d2.py
PYTHONPATH=. python agent_platform/voice/smoke_voice_proactive.py
PYTHONPATH=. python agent_platform/proactive/accept_m5_smoke.py
PYTHONPATH=. python agent_platform/proactive/accept_m5_us5.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_proactive_tools.py
```

详见 [docs/M5-proactive.md](../../docs/M5-proactive.md)、[docs/M5-us-acceptance.md](../../docs/M5-us-acceptance.md)。

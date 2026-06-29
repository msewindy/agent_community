# 感知层（M4）

| 里程碑 | 状态 |
|--------|------|
| D1 配置 + 契约 + mock/SDK 探测 | ✅ |
| D2 OpenCV 落盘 | ✅ |
| D3 Qwen2-VL 按需描述 | ✅ |
| D4 事件总线 + voice 联动 | ✅ |
| D5 统一验收 | ✅ |
| D6–D10 US-2 验收 + 签字 | ✅ 自动 |

```bash
# 一键 D1–D5
PYTHONPATH=. python agent_platform/perception/accept_m4_smoke.py

# US-2 正式验收（D6–D10）
PYTHONPATH=. python agent_platform/perception/accept_m4_us2.py

# 分项
PYTHONPATH=. python agent_platform/perception/smoke_perception_d1.py
```

详见 [docs/M4-smoke.md](../../docs/M4-smoke.md)、[docs/M4-us-acceptance.md](../../docs/M4-us-acceptance.md)。

详见 [docs/M4-reachy-perception.md](../../docs/M4-reachy-perception.md)。

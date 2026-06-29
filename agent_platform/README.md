# agent_platform

M1+ 业务代码层（语音、记忆适配等）。目录名 **不用** `platform`，避免与 Python 标准库 `platform` 冲突。

## 安装

```bash
conda activate hermes-agent
cd /home/lfw/project/agent_community
pip install -r agent_platform/requirements-voice.txt
pip install -r agent_platform/requirements-memory.txt   # M2
pip install -r agent_platform/requirements-wiki.txt      # M3
```

## M2 记忆（D1）

```bash
# MemVerse Docker（见 docs/M2-memory.md §6）
source agent_platform/deploy/memverse/env.sh
docker compose -f agent_platform/deploy/memverse/docker-compose.yml up -d

# 门面冒烟（Mock 不依赖 Docker）
PYTHONPATH=. python agent_platform/memory/smoke_memory.py
PYTHONPATH=. python agent_platform/memory/smoke_memory.py --memverse
PYTHONPATH=. python agent_platform/memory/smoke_memverse_e2e.py   # D4 门面 + MemVerse

# M2 D2–D5 契约 + Mock + Gate
cd agent_platform && PYTHONPATH=.. pytest -q
PYTHONPATH=. python agent_platform/memory/export_schema.py
PYTHONPATH=. python agent_platform/memory/cli_memory.py smoke-gate
PYTHONPATH=. python agent_platform/memory/cli_memory.py --gate write "偏好简短"

# M2 D6 审计链
PYTHONPATH=. python agent_platform/memory/cli_memory.py smoke-audit
PYTHONPATH=. python agent_platform/memory/cli_memory.py --audit --audit-db /tmp/audit.db audit <trace_id>

# M2 D7 记忆面板 US-7
PYTHONPATH=. python agent_platform/memory/smoke_panel.py
PYTHONPATH=. python -m agent_platform.api.memory_panel   # http://127.0.0.1:8765/

# M2 D8 / M3 D7 Hermes 工具
./agent_platform/integrations/hermes/install_plugin.sh
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_tools.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_wiki_tools.py

# M3 D8 US-4 验收
PYTHONPATH=. python agent_platform/wiki/accept_m3_us4.py

# M3 D9 M2+M3 联合召回
PYTHONPATH=. python agent_platform/integrations/demo_recall_m2_m3.py
PYTHONPATH=. python agent_platform/wiki/accept_m3_d9.py

# M4 D1 Reachy 感知骨架
pip install -r agent_platform/requirements-perception.txt
PYTHONPATH=. python agent_platform/perception/smoke_perception_d1.py
PYTHONPATH=. python agent_platform/perception/cli_perception.py init
PYTHONPATH=. python agent_platform/perception/cli_perception.py status

# M3 D10 签字 — 见 docs/M3-baseline.md
PYTHONPATH=. python agent_platform/wiki/accept_m3_smoke.py
# accept_m3_us4.py 与 accept_m3_d9.py 见上

# M2 D9 US-3 / US-7 验收
PYTHONPATH=. python agent_platform/memory/accept_m2_us.py

# M2 D10 文档见 docs/M2-baseline.md、docs/M2-M3-interface.md

# M3 Wiki（D5 汇总冒烟）
PYTHONPATH=. python agent_platform/wiki/smoke_wiki.py --isolated
PYTHONPATH=. python agent_platform/wiki/accept_m3_smoke.py

# M3 D1 Wiki 骨架
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d1.py
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py init
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py validate
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d2.py
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d3.py
PYTHONPATH=. python agent_platform/wiki/smoke_wiki_d4.py
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py query "topic"
PYTHONPATH=. python agent_platform/wiki/cli_wiki.py ingest raw/articles/note.md --topic "Topic"
```

## Smoke tests

```bash
export HF_HOME=/tmp/agent_voice_hf
export MODELSCOPE_CACHE=/tmp/agent_voice_modelscope

python agent_platform/voice/smoke_tts.py
python agent_platform/voice/smoke_vad.py          # 合成音
python agent_platform/voice/smoke_vad.py --mic    # 本机麦克风
python agent_platform/voice/smoke_asr.py          # 需先 smoke_tts；首次会下 ASR 模型
python agent_platform/voice/smoke_wake.py         # 唤醒词评分
python agent_platform/voice/smoke_mic_loop.py --seconds 5   # 麦→VAD→ASR
python agent_platform/voice/smoke_hermes.py -q "你好"       # Hermes 文本
python agent_platform/voice/smoke_pipeline.py -t "你好"    # 文本→Hermes→TTS
python agent_platform/voice/smoke_pipeline.py -t "看下桌上那本书叫什么名字？"  # M4 D4 视觉→Hermes→TTS
python agent_platform/perception/accept_m4_smoke.py       # M4 D5 一键验收
python agent_platform/perception/accept_m4_us2.py         # M4 D6–D10 US-2 验收

# M5 主动行为（US-5）
pip install -r agent_platform/requirements-proactive.txt
PYTHONPATH=. python agent_platform/proactive/smoke_proactive_d1.py
PYTHONPATH=. python agent_platform/proactive/smoke_proactive_d2.py
PYTHONPATH=. python agent_platform/proactive/accept_m5_smoke.py
PYTHONPATH=. python agent_platform/proactive/accept_m5_us5.py         # D6–D10 US-5 验收
PYTHONPATH=. python agent_platform/voice/smoke_voice_proactive.py
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_proactive_tools.py

# M6 MCP 工具 + L0–L2 治理（C2/C3）
pip install -r agent_platform/requirements-tools.txt
PYTHONPATH=. python agent_platform/tools/smoke_tools_d1.py
PYTHONPATH=. python agent_platform/tools/smoke_tools_d2.py
PYTHONPATH=. python agent_platform/tools/smoke_tools_d3.py
PYTHONPATH=. python agent_platform/tools/smoke_draft_panel.py
PYTHONPATH=. python -m agent_platform.api.draft_panel   # L2 草稿 http://127.0.0.1:8766/
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_tools_mcp.py
PYTHONPATH=. python agent_platform/tools/accept_m6_smoke.py
PYTHONPATH=. python agent_platform/tools/accept_m6_us.py
PYTHONPATH=. python agent_platform/tools/cli_tools.py status

# M7 校准 + 行为一致性档（US-6 / US-3）
PYTHONPATH=. python agent_platform/calibration/smoke_calibration_d1.py
PYTHONPATH=. python agent_platform/behavior/smoke_settings_panel.py
PYTHONPATH=. python -m agent_platform.api.settings_panel   # 设定 http://127.0.0.1:8767/
PYTHONPATH=. python agent_platform/integrations/hermes/smoke_hermes_calibration_tools.py
PYTHONPATH=. python agent_platform/calibration/accept_m7_smoke.py
PYTHONPATH=. python agent_platform/calibration/accept_m7_us.py
PYTHONPATH=. python agent_platform/calibration/accept_m7_manual.py
cd agent_platform && PYTHONPATH=.. pytest tests/test_calibration.py tests/test_behavior.py tests/test_m7_accept.py -q

# M8 集成 + v1 签字（8 US + 7 天自用）
PYTHONPATH=. python agent_platform/integration/accept_m8_integration.py --skip-us2
PYTHONPATH=. python agent_platform/integration/accept_m8_smoke.py
PYTHONPATH=. python agent_platform/integration/diary_check.py docs/M8-seven-day-diary.md  # 模板未填会 INCOMPLETE
cd agent_platform && PYTHONPATH=.. pytest tests/test_m8_accept.py tests/test_m8_integration.py -q

python agent_platform/perception/smoke_perception_d4.py   # 事件总线 + 编排（无需 Hermes）
python agent_platform/voice/smoke_pipeline.py --mic        # 麦→VAD→ASR→Hermes→TTS（会播放）
python agent_platform/voice/smoke_pipeline.py --wake       # 唤醒词→麦→全链路
python agent_platform/voice/smoke_pipeline.py -t "你好" --barge-in
python agent_platform/voice/smoke_barge_in.py --recover  # 打断演示
python agent_platform/voice/bench_m1.py                    # M1.6 时延基准
```

#!/usr/bin/env python3
"""将 Hermes 文档摘录全文并行翻译为中文。"""
from __future__ import annotations

import re
import time
import json
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from deep_translator import GoogleTranslator

SRC = Path("/tmp/hermes-llms-full.txt")
OUT = Path("/home/lfw/project/agent_community/Hermes-Agent-官方文档摘录-中文版.md")
PROGRESS = Path("/home/lfw/project/agent_community/.hermes-translate-progress.json")
BASE = "https://hermes-agent.nousresearch.com/docs"
CHUNK = 4500
WORKERS = 6
DELAY = 0.15

INTEGRATION_IN_FEATURES = {
    "website/docs/user-guide/features/mcp.md",
    "website/docs/user-guide/features/acp.md",
    "website/docs/user-guide/features/api-server.md",
    "website/docs/user-guide/features/honcho.md",
    "website/docs/user-guide/features/provider-routing.md",
    "website/docs/user-guide/features/fallback-providers.md",
    "website/docs/user-guide/features/credential-pools.md",
}

FEATURE_ORDER = [
    "overview", "tools", "tool-gateway", "skills", "curator", "memory", "memory-providers",
    "context-files", "context-references", "personality", "plugins", "built-in-plugins",
    "cron", "delegation", "kanban", "kanban-tutorial", "kanban-worker-lanes", "goals",
    "code-execution", "hooks", "batch-processing", "voice-mode", "browser", "vision",
    "image-generation", "tts", "web-search", "x-search", "lsp", "computer-use",
    "deliverable-mode", "web-dashboard", "extending-the-dashboard", "codex-app-server-runtime",
    "subscription-proxy", "spotify", "skins",
]

MESSAGING_ORDER = [
    "index", "telegram", "discord", "slack", "whatsapp", "signal", "email", "sms",
    "matrix", "mattermost", "homeassistant", "webhooks", "teams", "teams-meetings",
    "line", "dingtalk", "feishu", "wecom", "wecom-callback", "weixin", "qqbot",
    "yuanbao", "google_chat", "bluebubbles", "simplex", "open-webui", "msgraph-webhook",
]

GUIDE_ORDER = [
    "tips", "local-llm-on-mac", "local-ollama-setup", "daily-briefing-bot",
    "team-telegram-assistant", "python-library", "use-mcp-with-hermes",
    "use-voice-mode-with-hermes", "use-soul-with-hermes", "build-a-hermes-plugin",
    "automate-with-cron", "work-with-skills", "delegation-patterns",
    "github-pr-review-agent", "automation-templates", "cron-script-only",
    "cron-troubleshooting", "webhook-github-pr-review", "pipe-script-output",
    "migrate-from-openclaw", "aws-bedrock", "azure-foundry", "google-gemini",
    "minimax-oauth", "xai-grok-oauth", "oauth-over-ssh",
    "microsoft-graph-app-registration", "operate-teams-meeting-pipeline",
]


def load_sections() -> dict[str, str]:
    text = SRC.read_text(encoding="utf-8")
    pattern = re.compile(r"<!-- source: (website/docs/[^>]+) -->\n")
    parts = pattern.split(text)
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            sections[parts[i].strip()] = parts[i + 1]
    return sections


def order_paths(paths: list[str], order_stems: list[str]) -> list[str]:
    stem_map = {Path(p).stem: p for p in paths}
    ordered = [stem_map[s] for s in order_stems if s in stem_map]
    ordered += [p for p in sorted(paths) if p not in ordered]
    return ordered


def is_path_h1(t: str) -> bool:
    return "/" in t or t.endswith(".md") or t.startswith("user-guide")


def extract_title(path: str, content: str) -> str:
    for line in content.strip().split("\n")[:40]:
        if line.startswith("# "):
            t = line[2:].strip()
            if t and not is_path_h1(t):
                return t
    return Path(path).stem.replace("-", " ").title()


def clean_content(content: str) -> str:
    lines = content.strip().split("\n")
    while lines and lines[0].startswith("# ") and is_path_h1(lines[0][2:].strip()):
        lines = lines[1:]
    while len(lines) >= 2 and lines[0].startswith("# ") and lines[1].startswith("# ") and lines[0] == lines[1]:
        lines = lines[1:]
    return "\n".join(lines).strip()


def split_code_fences(md: str) -> list[str]:
    """按行状态机切分代码块，避免正则回溯卡顿。"""
    parts: list[str] = []
    buf: list[str] = []
    in_fence = False
    for line in md.split("\n"):
        if line.strip().startswith("```"):
            if in_fence:
                buf.append(line)
                parts.append("\n".join(buf) + "\n")
                buf = []
                in_fence = False
            else:
                if buf:
                    parts.append("\n".join(buf))
                    buf = []
                in_fence = True
                buf.append(line)
        else:
            buf.append(line)
    if buf:
        parts.append("\n".join(buf))
    return parts


def _translate_chunk(text: str, retries: int = 4) -> str:
    tr = GoogleTranslator(source="en", target="zh-CN")
    for attempt in range(retries):
        try:
            result = tr.translate(text)
            if result is None:
                raise ValueError("translator returned None")
            return result
        except Exception:
            if attempt == retries - 1:
                return text  # 失败时保留英文原文
            time.sleep(1.5 * (attempt + 1))
    return text


def translate_text(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if len(text) <= CHUNK:
        result = _translate_chunk(text)
        time.sleep(DELAY)
        return result
    out = []
    for i in range(0, len(text), CHUNK):
        out.append(_translate_chunk(text[i : i + CHUNK]))
        time.sleep(DELAY)
    return "".join(out)


def translate_markdown(md: str) -> str:
    parts = split_code_fences(md)
    result = []
    for part in parts:
        if part.lstrip().startswith("```"):
            result.append(part)
            continue
        if not part.strip():
            result.append(part)
            continue
        translated = translate_text(part)
        result.append(translated if translated is not None else part)
    return "".join(result)


def path_to_url(path: str) -> str:
    rel = path.replace("website/docs/", "").replace(".md", "")
    return f"{BASE}/{rel}"


def build_page_list(sections: dict[str, str]) -> list[tuple[str, str, str]]:
    all_features = [k for k in sections if k.startswith("website/docs/user-guide/features/")]
    feature_paths = order_paths(
        [p for p in all_features if p not in INTEGRATION_IN_FEATURES], FEATURE_ORDER
    )
    messaging_paths = order_paths(
        [k for k in sections if k.startswith("website/docs/user-guide/messaging/")],
        MESSAGING_ORDER,
    )
    integration_paths = (
        ["website/docs/integrations/index.md", "website/docs/integrations/providers.md"]
        + sorted([p for p in INTEGRATION_IN_FEATURES if p in sections])
    )
    guide_paths = order_paths(
        [k for k in sections if k.startswith("website/docs/guides/")], GUIDE_ORDER
    )
    meta = [
        ("一、Features（功能）", feature_paths),
        ("二、Messaging Platforms（消息平台）", messaging_paths),
        ("三、Integrations（集成）", integration_paths),
        ("四、Guides & Tutorials（指南与教程）", guide_paths),
    ]
    pages = []
    for label, paths in meta:
        for p in paths:
            if p in sections:
                pages.append((label, p, extract_title(p, sections[p])))
    return pages


def translate_one(path: str, title: str, body_en: str) -> dict:
    title_zh = translate_text(title)
    body_zh = translate_markdown(body_en)
    url = path_to_url(path)
    zh_url = url.replace("/docs/", "/docs/zh-Hans/")
    block = (
        f"### {title_zh}\n\n"
        f"> 原文链接：[English]({url}) · [简体中文]({zh_url})\n\n"
        f"{body_zh}\n"
    )
    return {"title_zh": title_zh, "block": block}


def assemble_output(pages: list, done: dict) -> None:
    slug_counts: dict[str, int] = {}

    def slugify(text: str) -> str:
        s = text.lower()
        s = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", s)
        return re.sub(r"\s+", "-", s.strip()) or "section"

    out: list[str] = []
    total = len(pages)
    out.append("# Hermes Agent 官方文档摘录（中文版）\n\n")
    out.append(f"> 来源：[Hermes Agent 官方文档](https://hermes-agent.nousresearch.com/docs/zh-Hans/)\n\n")
    out.append(f"> 整理日期：{date.today().isoformat()}\n\n")
    out.append(
        f"> 本文档为官方文档 Features / Messaging / Integrations / Guides 全部子页面的"
        f"**完整正文中文译文**（共 {total} 篇）。代码块、命令与 URL 保持原文。\n\n"
    )
    out.append("---\n\n## 目录\n\n")

    current = None
    for label, path, title in pages:
        if label != current:
            out.append(f"\n- **{label}**\n")
            current = label
        title_zh = done[path]["title_zh"]
        base = slugify(title_zh)
        slug_counts[base] = slug_counts.get(base, 0) + 1
        anchor = base if slug_counts[base] == 1 else f"{base}-{slug_counts[base]}"
        out.append(f"  - [{title_zh}](#{anchor})\n")

    out.append("\n\n---\n\n")
    current = None
    for label, path, _ in pages:
        if label != current:
            out.append(f"## {label}\n\n")
            current = label
        out.append(done[path]["block"])
        out.append("\n---\n\n")

    OUT.write_text("".join(out), encoding="utf-8")


def main():
    sections = load_sections()
    pages = build_page_list(sections)
    done: dict[str, dict] = {}
    if PROGRESS.exists():
        done = json.loads(PROGRESS.read_text(encoding="utf-8"))

    pending = [(label, p, t) for label, p, t in pages if p not in done]
    print(f"共 {len(pages)} 篇，已完成 {len(done)}，待翻译 {len(pending)}", flush=True)

    def job(item):
        label, path, title = item
        body = clean_content(sections[path])
        return path, title, translate_one(path, title, body)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(job, item): item for item in pending}
        for fut in as_completed(futures):
            label, path, title = futures[fut]
            try:
                path, title, result = fut.result()
                done[path] = result
                PROGRESS.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
                print(f"✓ [{len(done)}/{len(pages)}] {title}", flush=True)
            except Exception as e:
                print(f"✗ 失败 {title}: {e}", flush=True)

    assemble_output(pages, done)
    print(f"已写入: {OUT} ({OUT.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()

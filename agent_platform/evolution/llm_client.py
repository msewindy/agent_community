"""OpenAI-compatible LLM client for C7 Phase 3 (optional, env-driven)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _load_env_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def load_llm_env() -> None:
    """Load Hermes .env paths without overriding existing env."""
    home = os.path.expanduser("~")
    for p in (
        os.path.join(home, ".hermes", ".env"),
        os.path.join(os.environ.get("HERMES_HOME", ""), ".env"),
    ):
        if p and os.path.isfile(p):
            _load_env_file(p)


def llm_config(cfg: dict | None = None) -> dict:
    cfg = cfg or {}
    llm = dict(cfg.get("llm") or {})
    load_llm_env()
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    base = os.environ.get("OPENAI_API_BASE") or llm.get("base_url") or "https://api.deepseek.com/v1"
    model = os.environ.get("OPENAI_MODEL") or llm.get("model") or "deepseek-chat"
    llm.setdefault("api_key", key)
    llm.setdefault("base_url", base.rstrip("/"))
    llm.setdefault("model", model)
    llm.setdefault("timeout_s", 30)
    llm.setdefault("max_tokens", 800)
    return llm


def llm_available(cfg: dict | None = None) -> bool:
    return bool(llm_config(cfg).get("api_key"))


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def chat_json(system: str, user: str, cfg: dict | None = None) -> Optional[dict[str, Any]]:
    """Return parsed JSON object from LLM, or None on failure."""
    llm = llm_config(cfg)
    if not llm.get("api_key"):
        return None
    try:
        import httpx
    except ImportError:
        logger.debug("httpx not installed; LLM path unavailable")
        return None

    url = f"{llm['base_url']}/chat/completions"
    payload = {
        "model": llm["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": int(llm.get("max_tokens", 800)),
    }
    headers = {
        "Authorization": f"Bearer {llm['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=float(llm.get("timeout_s", 30))) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_json_object(content)
    except Exception as e:
        logger.warning("evolution LLM call failed: %s", e)
        return None

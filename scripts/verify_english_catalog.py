#!/usr/bin/env python3
"""Verify沪教英语 catalog + optional live API check."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent_platform.learning.kp_catalog import get_kp_catalog_service, invalidate_kp_catalog_cache


def main() -> int:
    invalidate_kp_catalog_cache()
    catalog = get_kp_catalog_service()
    english = [u for u in catalog.catalog.units if u.subject == "英语"]
    print("catalog_path:", catalog._path)
    print("english_units:", len(english))
    for u in english:
        print(f"  {u.unit_id} · {u.unit_title} · {len(u.knowledge_points)} KP")
    starter = [u for u in english if u.unit_id == "english-g3-starter"]
    if starter:
        print("ERROR: english-g3-starter still present")
        return 1
    if len(english) < 10:
        print("ERROR: expected 10 english units")
        return 1

    try:
        with urllib.request.urlopen("http://127.0.0.1:8770/api/kp/catalog/info", timeout=3) as resp:
            info = json.loads(resp.read().decode())
        print("api_info:", json.dumps(info, ensure_ascii=False))
        with urllib.request.urlopen("http://127.0.0.1:8770/api/kp/catalog/tree", timeout=3) as resp:
            tree = json.loads(resp.read().decode())
        api_english = next((s for s in tree.get("subjects", []) if s.get("subject") == "英语"), None)
        if api_english:
            g3 = next((g for g in api_english.get("grades", []) if g.get("grade") == 3), None)
            n = len(g3.get("units", [])) if g3 else 0
            print("api_english_g3_units:", n)
            if n < 10:
                print("WARN: API still serving old catalog — restart 8770")
                return 2
    except Exception as exc:
        print("api_check_skipped:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

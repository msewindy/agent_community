#!/usr/bin/env python3
"""Quick PDF structure probe for G3 math/chinese textbooks."""
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

import fitz

BASE = _REPO / "三年级课本"
OUT = _REPO / "student_data" / "_textbook_ingest" / "probe_report.txt"
OUT.parent.mkdir(parents=True, exist_ok=True)

def find_pdf(keywords):
    for p in BASE.glob("*.pdf"):
        if all(k in p.name for k in keywords):
            return p
    return None

def probe_file(path: Path, out):
    doc = fitz.open(path)
    out.write(f"\n{'='*60}\nFILE: {path.name}\nPAGES: {len(doc)}\n{'='*60}\n")
    # TOC-like scan: find unit/chapter headers
    unit_hits = []
    exercise_hits = []
    for i in range(len(doc)):
        text = doc[i].get_text()
        for pat in [r"第[一二三四五六七八九十]+单元", r"Unit\s+\d+", r"练习", r"试一试", r"练一练", r"想一想", r"做一做", r"Listen", r"阅读", r"识字", r"写字", r"口语交际"]:
            if re.search(pat, text, re.I):
                unit_hits.append((i+1, pat, text[:120].replace("\n", " ")))
                break
        for pat in [r"计算", r"填空", r"选择", r"判断", r"应用题", r"口算", r"竖式", r"连一连", r"写一写", r"读一读", r"背诵"]:
            m = re.search(pat, text)
            if m:
                exercise_hits.append((i+1, pat))
    out.write(f"\nUnit/chapter marker pages (sample): {len(unit_hits)}\n")
    for pg, pat, snip in unit_hits[:15]:
        out.write(f"  p{pg} [{pat}]: {snip[:80]}...\n")
    out.write(f"\nExercise marker pages (sample): {len(exercise_hits)}\n")
    for pg, pat in exercise_hits[:20]:
        out.write(f"  p{pg} [{pat}]\n")
    # full page samples
    indices = sorted(set([0,1,2,3,4,5,6,7,8,9,10,15,20,30,40,50,60,70,80,90,100]))
    for i in indices:
        if i >= len(doc):
            continue
        text = doc[i].get_text()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        out.write(f"\n--- page {i+1} ({len(lines)} lines) ---\n")
        out.write("\n".join(lines[:30]))
        out.write("\n")
    doc.close()

with OUT.open("w", encoding="utf-8") as out:
    math_pdf = find_pdf(["数学", "沪"])
    chi_pdf = find_pdf(["语文"])
    if math_pdf:
        probe_file(math_pdf, out)
    else:
        out.write("MATH PDF not found\n")
    if chi_pdf:
        probe_file(chi_pdf, out)
    else:
        out.write("CHINESE PDF not found\n")

print(f"Wrote {OUT}")

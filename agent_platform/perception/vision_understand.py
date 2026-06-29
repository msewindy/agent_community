"""理解型 VLM：图像类型 + 结构化题项（切片12 / 切片08 产品化）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from agent_platform.perception._config import load_perception_config
from agent_platform.perception.vlm import build_vlm_adapter

UNDERSTAND_PROMPT = (
    "你是小学学习助手的图像理解模块。请仔细看这张图，判断它的类型并提取结构化信息。\n"
    "只输出一个 JSON，不要任何多余文字、不要代码块标记。JSON 结构：\n"
    "{\n"
    '  "image_type": "graded_homework(已批改作业) | blank_problem(纯题目未作答) | '
    'answered_unmarked(已作答未批改) | knowledge_page(课本或知识页) | other(其他)",\n'
    '  "summary": "一句话说明你看到了什么",\n'
    '  "items": [\n'
    '    {"stem": "题目原文(含数字和运算符)", "student_answer": "孩子写的答案，没有则空串", '
    '"is_correct": true/false/null, "teacher_mark": "✓ 或 ✗ 或 空"}\n'
    "  ]\n"
    "}\n"
    "规则：is_correct 依据老师的批改符号判断(对勾=true，叉/圈错=false，没批改=null)；"
    "红笔订正、圈出错误也算 false；看不清的字用□；多道题就在 items 里列多条。"
)

_IMAGE_TYPE_LABELS = {
    "graded_homework": "批改过的作业",
    "blank_problem": "题目",
    "answered_unmarked": "已作答未批改",
    "knowledge_page": "课本/知识页",
    "other": "图片",
}


class VisionItem(BaseModel):
    stem: str
    student_answer: str = ""
    is_correct: Optional[bool] = None
    teacher_mark: Optional[str] = None


class VisionUnderstandResult(BaseModel):
    vision_id: str = ""
    image_type: str = "other"
    summary: str = ""
    items: list[VisionItem] = Field(default_factory=list)
    frame_path: Optional[str] = None
    elapsed_ms: float = 0.0

    @property
    def stats(self) -> dict[str, int]:
        total = len(self.items)
        wrong = sum(1 for i in self.items if i.is_correct is False)
        correct = sum(1 for i in self.items if i.is_correct is True)
        uncertain = sum(1 for i in self.items if i.is_correct is None)
        return {
            "total": total,
            "wrong": wrong,
            "correct": correct,
            "uncertain": uncertain,
        }

    @property
    def card_title(self) -> str:
        label = _IMAGE_TYPE_LABELS.get(self.image_type.split("(")[0].strip(), "图片")
        st = self.stats
        if self.image_type.startswith("graded_homework") and st["total"]:
            return f"📷 {label} · {st['total']} 题"
        if st["total"]:
            return f"📷 {label} · {st['total']} 项"
        return f"📷 {label}"

    @property
    def card_subtitle(self) -> str:
        st = self.stats
        if self.image_type.startswith("graded_homework"):
            if st["wrong"]:
                return f"约 {st['wrong']} 题有错 · {self.summary[:60]}"
            return self.summary[:80] or "已读懂批改信息"
        return (self.summary or "已看清图片")[:80]


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _normalize_image_type(raw: str) -> str:
    s = (raw or "other").strip()
    if "(" in s:
        s = s.split("(")[0].strip()
    allowed = {
        "graded_homework",
        "blank_problem",
        "answered_unmarked",
        "knowledge_page",
        "other",
    }
    return s if s in allowed else "other"


def parse_vlm_understand_json(content: str) -> dict[str, Any]:
    m = _JSON_RE.search(content or "")
    if not m:
        raise ValueError("VLM response is not JSON")
    return json.loads(m.group(0))


def build_vision_adapter(cfg: Optional[dict] = None):
    pcfg = cfg or load_perception_config()
    vision = dict(pcfg.get("vision") or {})
    vision["provider"] = "openai_compatible"
    vision.setdefault("model", "qwen3-vl-plus")
    vision.setdefault("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vision.setdefault("api_key_env", "DASHSCOPE_API_KEY")
    vision["max_tokens"] = max(int(vision.get("max_tokens", 1024)), 1500)
    return build_vlm_adapter({"vision": vision})


def understand_image(image_path: Path, *, cfg: Optional[dict] = None) -> VisionUnderstandResult:
    import time

    adapter = build_vision_adapter(cfg)
    t0 = time.perf_counter()
    raw = adapter.describe(image_path, UNDERSTAND_PROMPT)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    parsed = parse_vlm_understand_json(raw)
    items_raw = parsed.get("items") or []
    items: list[VisionItem] = []
    for it in items_raw:
        if not isinstance(it, dict):
            continue
        stem = (it.get("stem") or "").strip()
        if not stem:
            continue
        ic = it.get("is_correct")
        if ic is not None:
            ic = bool(ic)
        items.append(
            VisionItem(
                stem=stem,
                student_answer=str(it.get("student_answer") or ""),
                is_correct=ic,
                teacher_mark=(it.get("teacher_mark") or "") or None,
            )
        )
    return VisionUnderstandResult(
        image_type=_normalize_image_type(str(parsed.get("image_type", "other"))),
        summary=str(parsed.get("summary") or "").strip(),
        items=items,
        frame_path=str(image_path),
        elapsed_ms=elapsed_ms,
    )


def format_vision_pre_llm_block(record: VisionUnderstandResult) -> str:
    """注入 pre_llm hook：供 Agent 编排，勿向用户朗读 JSON。"""
    items_json = json.dumps(
        [i.model_dump(mode="json") for i in record.items],
        ensure_ascii=False,
    )
    wrong_items = [i for i in record.items if i.is_correct is False]
    wrong_lines = [
        f"  - {i.stem}（学生答 {i.student_answer or '—'}，批改：错）"
        for i in wrong_items
    ]
    wrong_block = (
        "\n".join(wrong_lines)
        if wrong_lines
        else "  - （items 中暂无 is_correct=false 的题）"
    )
    return (
        f"\n\n## 本轮附带图像理解（vision_id={record.vision_id} · 勿向用户朗读 JSON）\n"
        f"- image_type: {record.image_type}\n"
        f"- summary: {record.summary}\n"
        f"- stats: {json.dumps(record.stats, ensure_ascii=False)}\n"
        f"- items: {items_json}\n\n"
        "### 入库 vs 口播（分层 · 必须遵守）\n"
        "- **入库**（classify_photo）：以 items.is_correct / 老师批改为准，**不要**自行改对错再入库。\n"
        "- **口播**（对孩子）：可验算讲理；若验算结果与 is_correct 不一致，**可以**温和告诉孩子「你算得好像是对的」"
        "并建议「让爸爸妈妈跟老师确认一下」，避免做对了还被说成错。\n"
        "- 明确算错的题（如 50-18=42）：按错题讲解练。\n"
        "- is_correct=null：向孩子确认，不要替老师判。\n"
        "- 口播「记好了」之前，记学情意图须先**成功** classify_photo。\n\n"
        f"#### 批改错题清单（口播时优先引用）\n{wrong_block}\n\n"
        "### 何时入库（P7 · 语义意图，非固定口令）\n"
        "- **记学情 / 复盘意图**（说法不限）：想记录错题、巩固薄弱、复盘卷子、把作业记进去、"
        "看看错哪并保存、帮我记一下错题… → 且 image_type 含 graded_homework → "
        "调用 classify_photo(items=上述 **全部** items)。\n"
        "- **讲解意图**：不会、教教、讲讲、怎么做… → **不要**对整页调用 classify_photo；"
        "针对相关题讲解；若孩子答错且想记「不会」，可对**单题** attempt_submit_freeform。\n"
        "- 讲解结束后，若尚未入库且孩子可能想留痕，可**可选**问一句：「要不要把这道记进学情？」"
        "（孩子同意再调工具，不要默认整页 classify）。\n"
        "- **上传图片本身 ≠ 入学情**；必须有记学情/复盘意图且你调工具后才入库。\n"
        "- 意图不明 → 用口语摘要 + 问要「讲解」还是「记进学情」。\n"
    )

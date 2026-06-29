"""拍批改作业归类器 + 置信度分流 + 待归类收件箱（切片10 / S-B）。

定位（对齐 L0 P7 灵活编排、功能架构 §7）：
- 这是一个**可被 Agent 编排的操作**（动词），不是"拍照=必走某管线"的状态机。
- 输入：已被 VLM 读出的题项（题面 / 学生答案 / 对错）。本模块只做「题 ↔ 知识点闭集匹配 +
  置信度三档分流 + 入学情 / 收件箱」，不负责识图本身。
- 守 D2（权威边界）：归类器只能在知识点目录的候选里选，**绝不臆造目录外 kp_id**；
  匹配不上的题落入待归类收件箱，由家长归类 / 触发补录 KP / 忽略。
- 复用切片09：错题以**知识点为主轴**入学情（错因码可选，此处默认留空）。
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.contracts import AttemptSubmitResult
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.store import _atomic_write_json, layout_for
from agent_platform.learning.student_context import StudentContextService

Tier = Literal["auto", "confirm", "inbox"]


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #
class GradedItem(BaseModel):
    """VLM 读出的一道已批改题。"""

    stem: str
    student_answer: str = ""
    is_correct: Optional[bool] = None  # 老师批改结论；None=对错未知
    source_image: Optional[str] = None


class KpCandidate(BaseModel):
    kp_id: str
    title: str
    subject: str
    unit_id: str


class MatchResult(BaseModel):
    kp_id: Optional[str] = None
    confidence: float = 0.0
    reason: Optional[str] = None


class ClassifiedItem(BaseModel):
    stem: str
    student_answer: str = ""
    is_correct: Optional[bool] = None
    matched_kp_id: Optional[str] = None
    kp_title: Optional[str] = None
    confidence: float = 0.0
    tier: Tier = "inbox"
    reason: Optional[str] = None
    source_image: Optional[str] = None


class TriageEntry(BaseModel):
    entry_id: str
    student_id: str
    stem: str
    student_answer: str = ""
    is_correct: Optional[bool] = None
    matched_kp_id: Optional[str] = None
    kp_title: Optional[str] = None
    confidence: float = 0.0
    tier: Tier = "inbox"
    reason: Optional[str] = None
    source_image: Optional[str] = None
    status: Literal["pending", "resolved", "dropped"] = "pending"
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_kp_id: Optional[str] = None
    resolved_attempt_id: Optional[str] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def route(
    kp_id: Optional[str],
    confidence: float,
    is_correct: Optional[bool],
    tau_high: float,
    tau_low: float,
) -> Tier:
    """三档分流（功能架构 §7）。"""
    if not kp_id:
        return "inbox"  # 闭集匹配不上 → 收件箱（守 D2，不臆造 KP）
    if is_correct is None:
        return "confirm"  # 挂上了 KP 但对错未知 → 待确认（不能直接入学情）
    if confidence >= tau_high:
        return "auto"
    if confidence >= tau_low:
        return "confirm"
    return "inbox"


# --------------------------------------------------------------------------- #
# 匹配器（可插拔：Stub 用于确定性烟测 / Llm 用于真用）
# --------------------------------------------------------------------------- #
@runtime_checkable
class KpMatcher(Protocol):
    def match(
        self, stem: str, student_answer: str, candidates: list[KpCandidate]
    ) -> MatchResult: ...


class StubKpMatcher:
    """确定性匹配器：按 (子串 → kp_id, confidence) 规则命中第一条。仅用于测试。"""

    def __init__(self, rules: list[tuple[str, str, float]]) -> None:
        self._rules = rules

    def match(self, stem, student_answer, candidates) -> MatchResult:
        valid = {c.kp_id for c in candidates}
        text = f"{stem} {student_answer}"
        for needle, kp_id, conf in self._rules:
            if needle in text and kp_id in valid:
                return MatchResult(kp_id=kp_id, confidence=conf, reason=f"stub:{needle}")
        return MatchResult(kp_id=None, confidence=0.0, reason="stub:no-match")


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LlmKpMatcher:
    """OpenAI 兼容文本 LLM（默认 DeepSeek）做闭集归类：从候选里选一个 kp_id 或返回 null。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str = "deepseek-chat",
        api_key_env: str = "DEEPSEEK_API_KEY",
        api_key: Optional[str] = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self._api_key = api_key
        self.timeout_s = timeout_s

    @classmethod
    def from_config(cls, llm_cfg: dict) -> "LlmKpMatcher":
        base_env = llm_cfg.get("base_url_env", "DEEPSEEK_BASE_URL")
        base_url = os.environ.get(base_env) or "https://api.deepseek.com"
        return cls(
            base_url=base_url,
            model=str(llm_cfg.get("model", "deepseek-chat")),
            api_key_env=str(llm_cfg.get("api_key_env", "DEEPSEEK_API_KEY")),
            timeout_s=float(llm_cfg.get("timeout_s", 60)),
        )

    def _resolve_key(self) -> str:
        key = (self._api_key or os.environ.get(self.api_key_env) or "").strip()
        if not key:
            raise RuntimeError(f"Missing API key env: {self.api_key_env}")
        return key

    def match(self, stem, student_answer, candidates) -> MatchResult:
        valid = {c.kp_id for c in candidates}
        listing = "\n".join(f"- {c.kp_id} | {c.title}（{c.subject}）" for c in candidates)
        system = (
            "你是小学作业批改的知识点归类器。给你一道题和一份**知识点候选清单**，"
            "你只能从清单里挑出最匹配的一个 knowledge_point_id。"
            "如果清单里没有任何知识点能匹配这道题，必须返回 kp_id 为 null——"
            "**严禁臆造清单以外的 id，严禁硬凑**。"
            '只输出 JSON：{"kp_id": "<候选里的id>"或null, "confidence": 0~1的小数, "reason": "简短理由"}。'
        )
        user = (
            f"题面：{stem}\n"
            f"学生作答：{student_answer or '（空）'}\n\n"
            f"知识点候选清单：\n{listing}\n\n"
            "请按要求只输出 JSON。"
        )
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._resolve_key()}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return self._parse(content, valid)

    @staticmethod
    def _parse(content: str, valid: set[str]) -> MatchResult:
        m = _JSON_RE.search(content or "")
        if not m:
            return MatchResult(kp_id=None, confidence=0.0, reason="llm:unparseable")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return MatchResult(kp_id=None, confidence=0.0, reason="llm:bad-json")
        kp_id = obj.get("kp_id")
        if kp_id is not None and kp_id not in valid:
            # 守 D2：模型若臆造目录外 id，一律降为"无匹配"，转收件箱
            return MatchResult(
                kp_id=None,
                confidence=0.0,
                reason=f"llm:out-of-catalog({kp_id})",
            )
        try:
            conf = float(obj.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        return MatchResult(kp_id=kp_id, confidence=conf, reason=obj.get("reason"))


# --------------------------------------------------------------------------- #
# 服务
# --------------------------------------------------------------------------- #
class PhotoTriageService:
    def __init__(
        self,
        matcher: Optional[KpMatcher] = None,
        data_root: Optional[Path] = None,
        catalog: Optional[KpCatalogService] = None,
        ctx_svc: Optional[StudentContextService] = None,
        attempt_svc: Optional[AttemptService] = None,
        config: Optional[dict] = None,
    ) -> None:
        cfg = config or load_student_learning_config()
        pt = cfg.get("photo_triage") or {}
        self._tau_high = float(pt.get("tau_high", 0.85))
        self._tau_low = float(pt.get("tau_low", 0.60))
        self._data_root = data_root
        self._catalog = catalog or KpCatalogService(config=cfg)
        self._ctx = ctx_svc or StudentContextService(data_root=data_root)
        self._attempt = attempt_svc or AttemptService(
            data_root=data_root, context_svc=self._ctx, catalog=self._catalog
        )
        self._matcher = matcher or LlmKpMatcher.from_config(pt.get("llm") or {})

    # ---- 候选闭集 ---- #
    def candidates(self, student_id: str) -> list[KpCandidate]:
        grade_level: Optional[int] = None
        try:
            ctx = self._ctx.get(student_id)
            grade_level = ctx.curriculum.grade_level or self._catalog.resolve_grade_level(
                ctx.curriculum.grade
            )
        except Exception:
            grade_level = None
        out: list[KpCandidate] = []
        for unit in self._catalog.list_units(grade_level=grade_level):
            for kp in unit.knowledge_points:
                out.append(
                    KpCandidate(
                        kp_id=kp.knowledge_point_id,
                        title=kp.title,
                        subject=unit.subject,
                        unit_id=unit.unit_id,
                    )
                )
        return out

    # ---- 归类 + 分流 ---- #
    def classify(self, student_id: str, items: list[GradedItem]) -> list[ClassifiedItem]:
        cands = self.candidates(student_id)
        title_of = {c.kp_id: c.title for c in cands}
        valid = set(title_of)
        results: list[ClassifiedItem] = []
        for it in items:
            res = self._matcher.match(it.stem, it.student_answer, cands)
            kp_id = res.kp_id if res.kp_id in valid else None  # 守 D2
            tier = route(kp_id, res.confidence, it.is_correct, self._tau_high, self._tau_low)
            results.append(
                ClassifiedItem(
                    stem=it.stem,
                    student_answer=it.student_answer,
                    is_correct=it.is_correct,
                    matched_kp_id=kp_id,
                    kp_title=title_of.get(kp_id) if kp_id else None,
                    confidence=res.confidence,
                    tier=tier,
                    reason=res.reason,
                    source_image=it.source_image,
                )
            )
        return results

    # ---- 入学情 / 收件箱 ---- #
    def ingest(self, student_id: str, classified: list[ClassifiedItem]) -> dict:
        summary = {"auto": 0, "confirm": 0, "inbox": 0, "auto_attempt_ids": []}
        for c in classified:
            if c.tier == "auto" and c.matched_kp_id and c.is_correct is not None:
                res: AttemptSubmitResult = self._attempt.submit_freeform(
                    student_id,
                    stem=c.stem,
                    answer=c.student_answer,
                    correct=c.is_correct,
                    knowledge_point_id=c.matched_kp_id,
                    source="photo_auto",
                )
                summary["auto"] += 1
                summary["auto_attempt_ids"].append(res.attempt_id)
            else:
                self.inbox_append(student_id, c)
                summary[c.tier] += 1
        return summary

    def classify_and_ingest(self, student_id: str, items: list[GradedItem]) -> dict:
        classified = self.classify(student_id, items)
        summary = self.ingest(student_id, classified)
        summary["classified"] = [c.model_dump(mode="json") for c in classified]
        return summary

    # ---- 待归类收件箱持久化 ---- #
    def _inbox_path(self, student_id: str) -> Path:
        return layout_for(student_id, self._data_root).student_dir / "photo_inbox.json"

    def _load_inbox(self, student_id: str) -> list[TriageEntry]:
        path = self._inbox_path(student_id)
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [TriageEntry.model_validate(e) for e in raw]

    def _save_inbox(self, student_id: str, entries: list[TriageEntry]) -> None:
        layout_for(student_id, self._data_root).ensure_student_dir()
        payload = (
            json.dumps([e.model_dump(mode="json") for e in entries], ensure_ascii=False, indent=2)
            + "\n"
        )
        _atomic_write_json(self._inbox_path(student_id), payload)

    def inbox_append(self, student_id: str, item: ClassifiedItem) -> TriageEntry:
        entries = self._load_inbox(student_id)
        entry = TriageEntry(
            entry_id=_now().strftime("tri-%Y%m%d-%H%M%S-") + secrets.token_hex(2),
            student_id=student_id,
            stem=item.stem,
            student_answer=item.student_answer,
            is_correct=item.is_correct,
            matched_kp_id=item.matched_kp_id,
            kp_title=item.kp_title,
            confidence=item.confidence,
            tier=item.tier,
            reason=item.reason,
            source_image=item.source_image,
            status="pending",
            created_at=_now(),
        )
        entries.append(entry)
        self._save_inbox(student_id, entries)
        return entry

    def inbox_list(
        self, student_id: str, status: Optional[str] = "pending"
    ) -> list[TriageEntry]:
        entries = self._load_inbox(student_id)
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    def inbox_resolve(
        self,
        student_id: str,
        entry_id: str,
        knowledge_point_id: str,
        is_correct: bool,
        error_code: Optional[str] = None,
    ) -> AttemptSubmitResult:
        """家长把收件箱里某条归类到某 KP（D3：人工归类优先），入学情。"""
        entries = self._load_inbox(student_id)
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise KeyError(f"inbox entry not found: {entry_id}")
        if target.status != "pending":
            raise ValueError(f"inbox entry already {target.status}: {entry_id}")
        res = self._attempt.submit_freeform(
            student_id,
            stem=target.stem,
            answer=target.student_answer,
            correct=is_correct,
            error_code=error_code,
            knowledge_point_id=knowledge_point_id,
            source="photo_manual",
        )
        target.status = "resolved"
        target.resolved_at = _now()
        target.resolved_kp_id = knowledge_point_id
        target.resolved_attempt_id = res.attempt_id
        self._save_inbox(student_id, entries)
        return res

    def inbox_drop(self, student_id: str, entry_id: str) -> TriageEntry:
        entries = self._load_inbox(student_id)
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise KeyError(f"inbox entry not found: {entry_id}")
        target.status = "dropped"
        target.resolved_at = _now()
        self._save_inbox(student_id, entries)
        return target

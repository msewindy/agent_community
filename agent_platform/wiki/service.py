"""wiki_service facade — sole business entry for wiki I/O (M3)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_platform.wiki._config import load_wiki_config, resolve_store_root
from agent_platform.wiki.contracts import (
    WikiIngestRequest,
    WikiLintStubResult,
    WikiPageKind,
    WikiPageRef,
    WikiQueryRequest,
    WikiQueryResult,
    WikiSearchBackend,
)
from agent_platform.wiki.ingest import WikiIngestError, ingest_one
from agent_platform.wiki.precipitate import (
    PrecipitateConfig,
    PrecipitateDecision,
    PrecipitateSessionStore,
    evaluate_precipitate,
    load_precipitate_config,
    write_session_transcript,
)
from agent_platform.wiki.query import run_query
from agent_platform.wiki.store import WikiStoreLayout, ensure_store, layout_for


def _search_backend(cfg: dict) -> WikiSearchBackend:
    raw = (cfg.get("search") or {}).get("backend", "ripgrep")
    try:
        return WikiSearchBackend(str(raw))
    except ValueError:
        return WikiSearchBackend.ripgrep


def _default_page_kind(cfg: dict) -> WikiPageKind:
    raw = (cfg.get("ingest") or {}).get("default_kind", "concept")
    try:
        return WikiPageKind(str(raw))
    except ValueError:
        return WikiPageKind.concept


class WikiService:
    """Wiki facade — ingest (D2), query (D4), lint stub."""

    def __init__(
        self,
        config: Optional[dict] = None,
        store_root: Optional[Path] = None,
        layout: Optional[WikiStoreLayout] = None,
    ) -> None:
        self._cfg = config or load_wiki_config()
        root = store_root or resolve_store_root(self._cfg)
        if layout is not None:
            self._layout = layout
        elif self._cfg.get("store", {}).get("auto_init", True):
            self._layout = ensure_store(root)
        else:
            self._layout = layout_for(root)
        self._default_kind = _default_page_kind(self._cfg)
        self._search_backend = _search_backend(self._cfg)
        self._precipitate_cfg = load_precipitate_config(self._cfg)
        self._sessions = PrecipitateSessionStore(self._precipitate_cfg.state_path)

    @property
    def precipitate_config(self) -> PrecipitateConfig:
        return self._precipitate_cfg

    @property
    def store_root(self) -> Path:
        return self._layout.root

    @property
    def default_device_id(self) -> str:
        return (self._cfg.get("device") or {}).get("default_id", "default-device")

    def ingest(self, req: WikiIngestRequest) -> list[WikiPageRef]:
        """Minimal path: one raw file → one wiki page under wiki/concepts/ (configurable kind)."""
        ref = ingest_one(req, self._layout, default_kind=self._default_kind)
        return [ref]

    def query(self, req: WikiQueryRequest) -> WikiQueryResult:
        """Index-first, then ripgrep/qmd over wiki/ compiled pages."""
        return run_query(req, self._layout, backend=self._search_backend)

    def lint_stub(self) -> WikiLintStubResult:
        return WikiLintStubResult()

    def record_chat_turn(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        topic: Optional[str] = None,
    ) -> None:
        """Record a chat turn for precipitate evaluation (Hermes bridge D7)."""
        self._sessions.record_turn(session_id, role, text, topic=topic)  # type: ignore[arg-type]

    def evaluate_precipitate_offer(
        self,
        session_id: str,
        message: str = "",
        *,
        role: str = "user",
        topic: Optional[str] = None,
        record: bool = True,
    ) -> PrecipitateDecision:
        """Whether Agent should offer wiki ingest (D6)."""
        return evaluate_precipitate(
            session_id,
            message=message,
            role=role,  # type: ignore[arg-type]
            topic=topic,
            config=self._precipitate_cfg,
            store=self._sessions,
            record=record,
        )

    def mark_precipitate_declined(self, session_id: str) -> None:
        self._sessions.mark_declined(session_id)

    def draft_transcript_for_ingest(
        self,
        session_id: str,
        *,
        topic: Optional[str] = None,
    ) -> str:
        """Write session messages to raw/transcripts/; returns path for ingest."""
        st = self._sessions.get(session_id)
        return write_session_transcript(
            self._layout,
            session_id,
            st.messages,
            topic=topic or st.topic or "session",
        )

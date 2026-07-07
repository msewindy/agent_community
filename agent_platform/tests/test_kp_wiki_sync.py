"""P1-4 — KP → Wiki sync and explain_kp teaching context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_platform.integrations.hermes import student_tools as st
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_ingest_review import KpIngestReviewService, ResolutionAction
from agent_platform.learning.kp_wiki_sync import KpWikiSyncService, render_kp_wiki_markdown
from agent_platform.learning.textbook_ingest import TextbookIngestService

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"


@pytest.fixture
def wiki_env(tmp_path: Path):
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    wiki_root = tmp_path / "wiki_data"
    wiki = KpWikiSyncService(catalog=catalog, store_root=wiki_root)
    return catalog, wiki


def test_render_kp_wiki_markdown_includes_ids(wiki_env) -> None:
    catalog, _ = wiki_env
    unit = catalog.get_unit("math-g3-u01")
    kp = unit.knowledge_points[0]
    text = render_kp_wiki_markdown(
        kp=kp,
        unit=unit,
        description="先乘除后加减。",
    )
    assert kp.knowledge_point_id in text
    assert "先乘除后加减" in text
    assert "## 讲解要点" in text


def test_sync_unit_creates_raw_and_compiled(wiki_env) -> None:
    catalog, wiki = wiki_env
    unit = catalog.get_unit("math-g3-u01")
    report = wiki.sync_unit_from_catalog(unit, force=True)
    assert report.pages_synced == len(unit.knowledge_points)
    raw = wiki.raw_path_for_kp(unit.knowledge_points[0].knowledge_point_id)
    assert raw.is_file()
    assert (wiki.layout.concepts_dir).exists()


def test_fetch_teaching_context_prefers_raw(wiki_env) -> None:
    catalog, wiki = wiki_env
    unit = catalog.get_unit("math-g3-u01")
    kp_id = unit.knowledge_points[0].knowledge_point_id
    wiki.sync_unit_from_catalog(unit, force=True)
    ctx = wiki.fetch_teaching_context(kp_id)
    assert ctx["success"] is True
    assert ctx.get("source") == "raw"
    assert ctx.get("description_text")


def test_extract_description_from_raw() -> None:
    from agent_platform.learning.kp_wiki_sync import extract_description_from_raw_markdown

    body = "# Title\n\n## 讲解要点\n\n- hello word\n\n## 教学提示\n\n- tip"
    assert extract_description_from_raw_markdown(body) == "- hello word"


def test_fetch_teaching_context_after_sync(wiki_env) -> None:
    catalog, wiki = wiki_env
    unit = catalog.get_unit("math-g3-u01")
    kp_id = unit.knowledge_points[0].knowledge_point_id
    wiki.sync_unit_from_catalog(unit, force=True)
    ctx = wiki.fetch_teaching_context(kp_id)
    assert ctx["success"] is True
    assert ctx["has_wiki"] is True
    assert ctx["knowledge_point_id"] == kp_id


def test_explain_kp_tool(wiki_env, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog, wiki = wiki_env
    unit = catalog.get_unit("math-g3-u01")
    kp_id = unit.knowledge_points[0].knowledge_point_id
    wiki.sync_unit_from_catalog(unit, force=True)
    monkeypatch.setattr(
        "agent_platform.learning.kp_wiki_sync.KpWikiSyncService",
        lambda *a, **k: wiki,
    )
    out = json.loads(st.explain_kp({"knowledge_point_id": kp_id}))
    assert out["success"] is True
    assert out["has_wiki"] is True


def test_approve_syncs_wiki(tmp_path: Path) -> None:
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    wiki_root = tmp_path / "wiki_data"
    wiki = KpWikiSyncService(catalog=catalog, store_root=wiki_root)
    ingest = TextbookIngestService(data_root=data)
    review = KpIngestReviewService(
        ingest_svc=ingest,
        catalog_svc=catalog,
        wiki_sync_svc=wiki,
    )
    job = ingest.submit_kp_document(CHINESE_SAMPLE)
    snapshot = review.build_snapshot(job)
    for conflict in snapshot.catalog_diff.conflicts:
        if conflict.kind.value == "subject_grade_mismatch":
            continue
        if conflict.kind.value == "kp_title_mismatch":
            review.set_resolution(job.job_id, conflict.conflict_id, ResolutionAction.use_draft)
        elif conflict.kind.value == "kp_missing_in_draft":
            review.set_resolution(job.job_id, conflict.conflict_id, ResolutionAction.use_catalog)
        elif conflict.kind.value == "kp_cross_unit":
            review.set_resolution(
                job.job_id,
                conflict.conflict_id,
                ResolutionAction.rename_draft,
                new_knowledge_point_id=f"{conflict.knowledge_point_id}-web",
            )

    result = review.approve(job.job_id)
    assert result.wiki_sync.pages_synced >= 1
    assert wiki.raw_path_for_kp("kp-g2-punct-comma").is_file()

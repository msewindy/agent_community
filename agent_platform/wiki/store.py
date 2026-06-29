"""Wiki store layout — create and validate Karpathy-style directory skeleton (M3 D1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_platform.wiki._config import load_wiki_config, resolve_store_root
from agent_platform.wiki.contracts import WikiStoreLayout

_RAW_SUBDIRS = ("articles", "papers", "transcripts", "assets")
_WIKI_SUBDIRS = ("entities", "concepts", "comparisons", "queries")

_INDEX_SEED = """# Wiki Index

> Agent-maintained catalog. One line per page. Updated on ingest.

## Entities

_(none yet)_

## Concepts

_(none yet)_

## Comparisons

_(none yet)_

## Queries

_(none yet)_
"""

_LOG_SEED = """# Wiki Log

Append-only chronicle of ingest/query actions.

"""

_SCHEMA_SEED = """# Wiki Schema — agent_community 阶段 A

## Domain

共域陪伴助理（Hermes + Reachy）相关的**主题知识**：技术笔记、资料消化、概念综述。  
**不**存放用户偏好/身份事实（→ `memory_service` / MemVerse）。

## Directory layout

```
{store_root}/
  SCHEMA.md       # 本文件
  index.md        # 目录 + 单行摘要
  log.md          # 操作日志（append-only）
  raw/            # 只读原料（Agent 不修改）
    articles/
    papers/
    transcripts/
    assets/
  wiki/           # 编译层（Agent 维护）
    entities/
    concepts/
    comparisons/
    queries/
```

## Conventions

- 文件名：小写、连字符、无空格（例：`mcp-architecture.md`）
- 每页 YAML frontmatter：`title`, `kind`, `updated`, `sources`（raw 路径列表）
- 交叉引用：`[[page-name]]` wikilink
- 新 ingest：更新相关 wiki 页 + `index.md` + `log.md` 一条

## Page kinds

| kind | 目录 | 用途 |
|------|------|------|
| entity | wiki/entities/ | 人物、组织、产品 |
| concept | wiki/concepts/ | 主题、技术概念 |
| comparison | wiki/comparisons/ | 并排对比 |
| archived_query | wiki/queries/ | 值得保留的问答归档 |

## Operations (M3)

| 操作 | 门面 | 说明 |
|------|------|------|
| ingest | `wiki_service.ingest` | raw → 多页 + index + log |
| query | `wiki_service.query` | 先 index，再相关页 |
| lint | `wiki_service.lint_stub` | v1 仅占位 |

## Boundary (M2)

- 用户偏好、项目状态 → `agent_memory_*` / MemVerse
- 深度讨论沉淀 → 本 Wiki
"""


def layout_for(root: Path) -> WikiStoreLayout:
    root = root.resolve()
    wiki = root / "wiki"
    return WikiStoreLayout(
        root=root,
        schema_path=root / "SCHEMA.md",
        index_path=root / "index.md",
        log_path=root / "log.md",
        raw_dir=root / "raw",
        wiki_dir=wiki,
        entities_dir=wiki / "entities",
        concepts_dir=wiki / "concepts",
        comparisons_dir=wiki / "comparisons",
        queries_dir=wiki / "queries",
    )


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _touch_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    keep = path / ".gitkeep"
    if not any(path.iterdir()):
        keep.write_text("", encoding="utf-8")


def ensure_store(
    root: Path | None = None,
    *,
    domain_note: str = "agent_community 阶段 A",
    force_log_entry: bool = False,
) -> WikiStoreLayout:
    """Create wiki skeleton if missing; never overwrite existing SCHEMA/index."""
    cfg = load_wiki_config()
    root = (root or resolve_store_root(cfg)).resolve()
    lay = layout_for(root)

    _touch_dir(lay.raw_dir)
    for sub in _RAW_SUBDIRS:
        _touch_dir(lay.raw_dir / sub)

    _touch_dir(lay.wiki_dir)
    for sub in _WIKI_SUBDIRS:
        _touch_dir(lay.wiki_dir / sub)

    schema_body = _SCHEMA_SEED.format(store_root=lay.root)
    _write_if_missing(lay.schema_path, schema_body)
    _write_if_missing(lay.index_path, _INDEX_SEED)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if _write_if_missing(lay.log_path, _LOG_SEED):
        entry = f"- {now} store initialized ({domain_note})\n"
        lay.log_path.write_text(lay.log_path.read_text(encoding="utf-8") + entry, encoding="utf-8")
    elif force_log_entry:
        entry = f"- {now} store ensure_store ({domain_note})\n"
        with lay.log_path.open("a", encoding="utf-8") as f:
            f.write(entry)

    return lay


def validate_store(root: Path | None = None) -> list[str]:
    """Return list of missing required paths (empty = OK)."""
    lay = layout_for(root or resolve_store_root())
    required = [
        lay.schema_path,
        lay.index_path,
        lay.log_path,
        lay.raw_dir,
        lay.wiki_dir,
        lay.entities_dir,
        lay.concepts_dir,
    ]
    missing: list[str] = []
    for p in required:
        if not p.exists():
            missing.append(str(p))
    return missing

"""M3 LLM Wiki layer — D1: contracts + store skeleton."""

from agent_platform.wiki.contracts import (
    SCHEMA_VERSION,
    WikiIngestRequest,
    WikiPageRef,
    WikiQueryRequest,
    WikiQueryResult,
    WikiPort,
)
from agent_platform.wiki.service import WikiService

__all__ = [
    "SCHEMA_VERSION",
    "WikiIngestRequest",
    "WikiPageRef",
    "WikiQueryRequest",
    "WikiQueryResult",
    "WikiPort",
    "WikiService",
]

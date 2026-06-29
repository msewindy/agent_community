"""Hermes plugin: agent-wiki — registers wiki_ingest / wiki_query tools."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    from agent_platform.integrations.hermes.recall_tools import register_recall_hermes_tools
    from agent_platform.integrations.hermes.wiki_tools import register_wiki_hermes_tools

    register_wiki_hermes_tools(ctx)
    register_recall_hermes_tools(ctx)
    logger.info(
        "agent-wiki plugin: wiki_ingest, wiki_query, wiki_precipitate_evaluate, "
        "agent_combined_recall"
    )

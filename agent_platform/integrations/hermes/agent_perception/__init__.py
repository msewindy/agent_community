"""Hermes plugin: agent-perception — US-2 describe + policy tools (M4 D3)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    from agent_platform.integrations.hermes.perception_tools import register_perception_hermes_tools

    register_perception_hermes_tools(ctx)
    logger.info(
        "agent-perception plugin: agent_perception_describe, agent_perception_policy"
    )

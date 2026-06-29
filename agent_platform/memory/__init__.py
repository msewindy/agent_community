"""M2 memory facade — business code must use memory_service, not MemVerse directly."""

from agent_platform.memory.audit import AuditStore
from agent_platform.memory.service import MemoryService, get_memory_service
from agent_platform.memory.trace import new_trace_id, trace_from_session

__all__ = [
    "MemoryService",
    "get_memory_service",
    "AuditStore",
    "new_trace_id",
    "trace_from_session",
]

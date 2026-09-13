"""Scoped persistent memory and semantic retrieval."""

from alos.memory.repository import (
    EmbeddingGateway,
    EmbeddingRequest,
    EmbeddingResponse,
    MemoryConfigurationError,
    MemoryCreateRequest,
    MemoryNotFoundError,
    MemoryRecord,
    MemoryRepository,
    SemanticMemoryQuery,
    SemanticMemoryResult,
)

__all__ = [
    "EmbeddingGateway",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "MemoryConfigurationError",
    "MemoryCreateRequest",
    "MemoryNotFoundError",
    "MemoryRecord",
    "MemoryRepository",
    "SemanticMemoryQuery",
    "SemanticMemoryResult",
]

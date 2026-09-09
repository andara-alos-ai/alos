"""Persistent, classification-aware memory with scope-first pgvector retrieval."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from alos.authorization import require_division, require_tenant, require_workspace
from alos.genesis.governed_foundations import MemoryKind, Scope
from alos.identity import HumanRole
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext

MemoryClassification = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]


class MemoryError(RuntimeError):
    """A safe memory service failure."""


class MemoryNotFoundError(MemoryError):
    """Memory is absent, expired, or outside the authenticated scope."""


class MemoryConfigurationError(MemoryError):
    """Semantic memory needs an embedding configuration that is not available."""


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=100_000)
    classification: MemoryClassification
    correlation_id: UUID


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    vector: tuple[float, ...] = Field(min_length=1, max_length=2_000)
    input_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


class EmbeddingGateway(Protocol):
    """ALOS-owned policy boundary; providers must implement only this contract."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MemoryKind
    scope: Scope
    classification: MemoryClassification = "INTERNAL"
    content: str = Field(min_length=1, max_length=100_000)
    source_reference: str = Field(min_length=1, max_length=2_000)
    lineage: dict[str, Any]
    retention_until: AwareDatetime
    idempotency_key: str = Field(min_length=1, max_length=200)
    create_embedding: bool = True


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    kind: MemoryKind
    scope: Scope
    classification: MemoryClassification
    content: str
    content_digest: str
    source_reference: str
    lineage: dict[str, Any]
    retention_until: datetime
    expired_at: datetime | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    embedding_status: Literal["READY", "NEEDS_CONFIGURATION"]
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimension: int | None
    content_trust: Literal["UNTRUSTED"] = "UNTRUSTED"


class SemanticMemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope
    query: str = Field(min_length=1, max_length=20_000)
    classifications: tuple[MemoryClassification, ...] = ("PUBLIC", "INTERNAL")
    limit: int = Field(default=10, ge=1, le=100)
    minimum_similarity: float = Field(default=0, ge=-1, le=1)


class SemanticMemoryResult(BaseModel):
    memory: MemoryRecord
    similarity: float


class MemoryRepository:
    """Apply authorization filters in SQL before cosine similarity ranking."""

    _SELECT = """
        entry.memory_id, entry.kind, entry.organization_id, entry.workspace_id,
        entry.division_id, entry.project_id, entry.tenant_id, entry.classification,
        entry.content, entry.content_digest, entry.source_reference, entry.lineage,
        entry.retention_until, entry.expired_at, entry.created_by_user_id,
        entry.created_at, entry.updated_at, embedding.provider AS embedding_provider,
        embedding.model AS embedding_model, embedding.dimension AS embedding_dimension
    """

    def __init__(
        self, database_url: str, embedding_gateway: EmbeddingGateway | None = None
    ) -> None:
        self._database_url = psycopg_url(database_url)
        self._embedding_gateway = embedding_gateway

    def create(
        self,
        request: MemoryCreateRequest,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> MemoryRecord:
        self._authorize_request_scope(actor, request.scope)
        self._require_classification(actor, request.classification)
        now = datetime.now(UTC)
        if request.retention_until <= now:
            raise MemoryError("memory retention must end in the future")
        embedding = None
        if request.create_embedding:
            if self._embedding_gateway is None:
                raise MemoryConfigurationError("embedding gateway is not configured")
            embedding = self._embedding_gateway.embed(
                EmbeddingRequest(
                    text=request.content,
                    classification=request.classification,
                    correlation_id=correlation_id,
                )
            )
            self._validate_vector(embedding.vector)
        digest = hashlib.sha256(request.content.encode("utf-8")).hexdigest()
        with self._transaction() as connection:
            self._require_database_scope(connection, actor, request.scope)
            row = connection.execute(
                """
                INSERT INTO memory.entries (
                    organization_id, workspace_id, division_id, project_id, tenant_id,
                    kind, classification, content, content_digest, source_reference,
                    lineage, retention_until, created_by_user_id, idempotency_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (organization_id, created_by_user_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING memory_id
                """,
                (
                    request.scope.organization_id,
                    request.scope.workspace_id,
                    request.scope.division_id,
                    request.scope.project_id,
                    request.scope.tenant_id,
                    request.kind.value,
                    request.classification,
                    request.content,
                    digest,
                    request.source_reference,
                    Jsonb(request.lineage),
                    request.retention_until,
                    actor.user_id,
                    request.idempotency_key,
                ),
            ).fetchone()
            if row is None:
                raise MemoryError("memory could not be persisted")
            memory_id = row["memory_id"]
            existing = connection.execute(
                """
                SELECT content_digest, source_reference FROM memory.entries
                WHERE memory_id = %s
                """,
                (memory_id,),
            ).fetchone()
            if existing is None or existing["content_digest"] != digest:
                raise MemoryError("idempotency key is bound to different memory content")
            if existing["source_reference"] != request.source_reference:
                raise MemoryError("idempotency key is bound to a different memory source")
            if embedding is not None:
                connection.execute(
                    """
                    INSERT INTO memory.embeddings (
                        memory_id, provider, model, dimension, embedding,
                        input_tokens, estimated_cost_usd
                    ) VALUES (%s, %s, %s, %s, %s::vector, %s, %s)
                    ON CONFLICT (memory_id) DO NOTHING
                    """,
                    (
                        memory_id,
                        embedding.provider,
                        embedding.model,
                        len(embedding.vector),
                        self._vector_text(embedding.vector),
                        embedding.input_tokens,
                        embedding.estimated_cost_usd,
                    ),
                )
            self._audit(
                connection,
                actor,
                action="SCOPED_MEMORY_CREATED",
                entity_id=memory_id,
                correlation_id=correlation_id,
                metadata={
                    "classification": request.classification,
                    "embedding": embedding is not None,
                    "content_digest": digest,
                },
            )
            return self._load(connection, memory_id, actor, include_expired=False)

    def get(self, memory_id: UUID, actor: ActorContext) -> MemoryRecord:
        with self._connection() as connection:
            return self._load(connection, memory_id, actor, include_expired=False)

    def list_scoped(
        self,
        scope: Scope,
        actor: ActorContext,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        self._authorize_request_scope(actor, scope)
        with self._connection() as connection:
            self._require_database_scope(connection, actor, scope)
            rows = connection.execute(
                f"""
                SELECT {self._SELECT}
                FROM memory.entries AS entry
                LEFT JOIN memory.embeddings AS embedding USING (memory_id)
                WHERE entry.organization_id = %s AND entry.workspace_id = %s
                  AND entry.tenant_id IS NOT DISTINCT FROM %s
                  AND entry.division_id IS NOT DISTINCT FROM %s
                  AND entry.project_id IS NOT DISTINCT FROM %s
                  AND entry.expired_at IS NULL AND entry.retention_until > now()
                  AND entry.classification = ANY(%s)
                ORDER BY entry.created_at DESC, entry.memory_id DESC
                LIMIT %s OFFSET %s
                """,
                (
                    scope.organization_id,
                    scope.workspace_id,
                    scope.tenant_id,
                    scope.division_id,
                    scope.project_id,
                    list(self._allowed_classifications(actor)),
                    min(max(limit, 1), 200),
                    max(offset, 0),
                ),
            ).fetchall()
        return [self._record(row) for row in rows]

    def expire(
        self,
        memory_id: UUID,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> MemoryRecord:
        with self._transaction() as connection:
            current = self._load(connection, memory_id, actor, include_expired=True)
            if current.expired_at is not None:
                return current
            row = connection.execute(
                """
                UPDATE memory.entries SET expired_at = now(), updated_at = now()
                WHERE memory_id = %s RETURNING memory_id
                """,
                (memory_id,),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError("memory was not found")
            self._audit(
                connection,
                actor,
                action="SCOPED_MEMORY_EXPIRED",
                entity_id=memory_id,
                correlation_id=correlation_id,
                metadata={"content_digest": current.content_digest},
            )
            return self._load(connection, memory_id, actor, include_expired=True)

    def semantic_search(
        self,
        request: SemanticMemoryQuery,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> list[SemanticMemoryResult]:
        self._authorize_request_scope(actor, request.scope)
        allowed = set(self._allowed_classifications(actor))
        if not request.classifications or not set(request.classifications).issubset(allowed):
            raise MemoryNotFoundError("requested memory classification is not authorized")
        if self._embedding_gateway is None:
            raise MemoryConfigurationError("embedding gateway is not configured")
        query_embedding = self._embedding_gateway.embed(
            EmbeddingRequest(
                text=request.query,
                classification=max(
                    request.classifications,
                    key=("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED").index,
                ),
                correlation_id=correlation_id,
            )
        )
        self._validate_vector(query_embedding.vector)
        vector = self._vector_text(query_embedding.vector)
        scope = request.scope
        with self._connection() as connection:
            self._require_database_scope(connection, actor, scope)
            rows = connection.execute(
                f"""
                WITH scoped AS (
                    SELECT {self._SELECT}, embedding.embedding
                    FROM memory.entries AS entry
                    JOIN memory.embeddings AS embedding USING (memory_id)
                    WHERE entry.organization_id = %s AND entry.workspace_id = %s
                      AND entry.tenant_id IS NOT DISTINCT FROM %s
                      AND entry.division_id IS NOT DISTINCT FROM %s
                      AND entry.project_id IS NOT DISTINCT FROM %s
                      AND entry.expired_at IS NULL AND entry.retention_until > now()
                      AND entry.classification = ANY(%s)
                      AND embedding.dimension = %s
                ), ranked AS (
                    SELECT scoped.*, 1 - (scoped.embedding <=> %s::vector) AS similarity
                    FROM scoped
                )
                SELECT * FROM ranked WHERE similarity >= %s
                ORDER BY similarity DESC, created_at DESC LIMIT %s
                """,
                (
                    scope.organization_id,
                    scope.workspace_id,
                    scope.tenant_id,
                    scope.division_id,
                    scope.project_id,
                    list(request.classifications),
                    len(query_embedding.vector),
                    vector,
                    request.minimum_similarity,
                    request.limit,
                ),
            ).fetchall()
        return [
            SemanticMemoryResult(memory=self._record(row), similarity=float(row["similarity"]))
            for row in rows
        ]

    def _load(
        self,
        connection: psycopg.Connection[Any],
        memory_id: UUID,
        actor: ActorContext,
        *,
        include_expired: bool,
    ) -> MemoryRecord:
        expiry = (
            ""
            if include_expired
            else "AND entry.expired_at IS NULL AND entry.retention_until > now()"
        )
        tenant_condition = (
            "AND (entry.tenant_id IS NULL OR entry.tenant_id = ANY(%s))"
            if actor.tenant_ids
            else "AND entry.tenant_id IS NULL"
        )
        params: list[Any] = [memory_id, actor.organization_id, actor.workspace_ids]
        if actor.tenant_ids:
            params.append(actor.tenant_ids)
        params.append(list(self._allowed_classifications(actor)))
        row = connection.execute(
            f"""
            SELECT {self._SELECT}
            FROM memory.entries AS entry
            LEFT JOIN memory.embeddings AS embedding USING (memory_id)
            WHERE entry.memory_id = %s AND entry.organization_id = %s
              AND entry.workspace_id = ANY(%s) {tenant_condition} {expiry}
              AND entry.classification = ANY(%s)
            """,
            params,
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError("memory was not found")
        record = self._record(row)
        self._authorize_request_scope(actor, record.scope)
        self._require_database_scope(connection, actor, record.scope)
        return record

    @staticmethod
    def _record(row: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            kind=row["kind"],
            scope=Scope(
                organization_id=row["organization_id"],
                workspace_id=row["workspace_id"],
                division_id=row["division_id"],
                project_id=row["project_id"],
                tenant_id=row["tenant_id"],
            ),
            classification=row["classification"],
            content=row["content"] or "",
            content_digest=row["content_digest"],
            source_reference=row["source_reference"],
            lineage=row["lineage"],
            retention_until=row["retention_until"],
            expired_at=row["expired_at"],
            created_by_user_id=row["created_by_user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            embedding_status=(
                "READY" if row["embedding_dimension"] is not None else "NEEDS_CONFIGURATION"
            ),
            embedding_provider=row["embedding_provider"],
            embedding_model=row["embedding_model"],
            embedding_dimension=row["embedding_dimension"],
        )

    @staticmethod
    def _authorize_request_scope(actor: ActorContext, scope: Scope) -> None:
        if scope.organization_id != actor.organization_id:
            raise MemoryNotFoundError("memory scope is outside the organization")
        require_workspace(actor, scope.workspace_id)
        require_tenant(actor, scope.tenant_id)

    @staticmethod
    def _require_database_scope(
        connection: psycopg.Connection[Any], actor: ActorContext, scope: Scope
    ) -> None:
        row = connection.execute(
            """
            SELECT division.code AS division_code
            FROM workspace.workspaces AS workspace
            JOIN workspace.memberships AS membership
              ON membership.workspace_id = workspace.workspace_id
            JOIN identity.users AS actor_user ON actor_user.user_id = membership.user_id
            LEFT JOIN identity.divisions AS division ON division.division_id = %s
            WHERE workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE' AND membership.user_id = %s
              AND actor_user.organization_id = %s AND actor_user.status = 'ACTIVE'
              AND (%s::uuid IS NULL OR division.organization_id = %s)
            """,
            (
                scope.division_id,
                scope.workspace_id,
                actor.organization_id,
                actor.user_id,
                actor.organization_id,
                scope.division_id,
                actor.organization_id,
            ),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError("active scoped workspace membership is required")
        if scope.division_id is not None:
            require_division(actor, row["division_code"])
        if scope.project_id is not None:
            project = connection.execute(
                """
                SELECT 1 FROM portfolio.projects
                WHERE project_id = %s AND organization_id = %s AND workspace_id = %s
                  AND (%s::uuid IS NULL OR division_id = %s) AND status <> 'ARCHIVED'
                """,
                (
                    scope.project_id,
                    actor.organization_id,
                    scope.workspace_id,
                    scope.division_id,
                    scope.division_id,
                ),
            ).fetchone()
            if project is None:
                raise MemoryNotFoundError("memory project is outside the authorized scope")

    @staticmethod
    def _allowed_classifications(actor: ActorContext) -> tuple[MemoryClassification, ...]:
        values: list[MemoryClassification] = ["PUBLIC", "INTERNAL"]
        if "memory.confidential.read" in actor.permissions or HumanRole.DIRECTOR in actor.roles:
            values.append("CONFIDENTIAL")
        if "memory.restricted.read" in actor.permissions and HumanRole.DIRECTOR in actor.roles:
            values.append("RESTRICTED")
        return tuple(values)

    @classmethod
    def _require_classification(
        cls, actor: ActorContext, classification: MemoryClassification
    ) -> None:
        if classification not in cls._allowed_classifications(actor):
            raise MemoryNotFoundError("memory classification is not authorized")

    @staticmethod
    def _validate_vector(vector: tuple[float, ...]) -> None:
        if not vector or len(vector) > 2_000 or any(not math.isfinite(value) for value in vector):
            raise MemoryConfigurationError("embedding vector is invalid")

    @staticmethod
    def _vector_text(vector: tuple[float, ...]) -> str:
        return "[" + ",".join(format(value, ".17g") for value in vector) + "]"

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        *,
        action: str,
        entity_id: UUID,
        correlation_id: UUID,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, 'SCOPED_MEMORY', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                action,
                entity_id,
                correlation_id,
                "Scoped memory state changed through the governed repository",
                Jsonb(metadata),
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with self._connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

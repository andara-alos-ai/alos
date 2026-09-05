"""Append-only Source Registry used by Genesis and the shared Runtime.

This MVP stores only textual extracts supplied by an authenticated internal
user.  It deliberately does not fetch URLs, parse untrusted binaries, or make
external calls.  Those capabilities require separately reviewed tools.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alos.persistence.database import psycopg_url

SourceType = Literal["DOCX", "PDF", "TEXT", "URL"]
SourceClassification = Literal["PUBLIC", "INTERNAL"]
_GOOGLE_DRIVE_FOLDER_URL = re.compile(
    r"^https://drive\.google\.com/drive/folders/([A-Za-z0-9_-]{10,})(?:[/?#].*)?$"
)


class SourceRegistryError(RuntimeError):
    """A safe Source Registry error suitable for API output."""


class SourceConflictError(SourceRegistryError):
    """An immutable source/version identity was reused inconsistently."""


class SourceNotFoundError(SourceRegistryError):
    """A requested source is unavailable within the actor workspace."""


class SourceVaultPolicyRequest(BaseModel):
    """Human-approved source boundary for a controlled H5 pilot.

    A Source Vault records an allowed Drive root and a separately denied folder.
    It never grants the Runtime a Drive token or permission to fetch Drive.
    """

    model_config = ConfigDict(extra="forbid")

    allowed_root_url: str = Field(min_length=20, max_length=2_000)
    excluded_folder_url: str = Field(min_length=20, max_length=2_000)
    reason: str = Field(min_length=10, max_length=10_000)

    @model_validator(mode="after")
    def validate_distinct_google_drive_folders(self) -> SourceVaultPolicyRequest:
        if _google_drive_folder_id(self.allowed_root_url) is None:
            raise ValueError("allowed_root_url must be a Google Drive folder URL")
        if _google_drive_folder_id(self.excluded_folder_url) is None:
            raise ValueError("excluded_folder_url must be a Google Drive folder URL")
        if _google_drive_folder_id(self.allowed_root_url) == _google_drive_folder_id(
            self.excluded_folder_url
        ):
            raise ValueError("allowed and excluded Drive folders must be different")
        return self


class SourceVaultPolicyRecord(BaseModel):
    source_vault_policy_id: UUID
    workspace_id: UUID
    allowed_root_url: str
    excluded_folder_url: str
    access_mode: Literal["READ_ONLY"]
    created_at: datetime
    updated_at: datetime


class SourceRegistrationRequest(BaseModel):
    """Human-provided textual extract; no provider or network call is involved."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    source_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType = "TEXT"
    classification: SourceClassification = "INTERNAL"
    version_label: str = Field(min_length=1, max_length=100)
    locator: str | None = Field(default=None, max_length=2_000)
    content: str = Field(min_length=1, max_length=200_000)
    source_vault_policy_id: UUID | None = None
    vault_attestation: bool = False

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source content must not be blank")
        return value


class SourceVersionRecord(BaseModel):
    source_id: UUID
    source_version_id: UUID
    workspace_id: UUID
    source_key: str
    name: str
    source_type: SourceType
    classification: SourceClassification
    status: str
    version_label: str
    sha256: str
    locator: str | None
    citation_count: int
    source_vault_policy_id: UUID | None = None


class SourceVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    reason: str = Field(min_length=1, max_length=10_000)


class EvidenceCitation(BaseModel):
    citation_key: str
    source_key: str
    version_label: str
    locator: str | None
    anchor: str
    excerpt: str


class SourceRegistryRepository:
    """PostgreSQL Source Registry with explicit human verification."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def register(
        self,
        request: SourceRegistrationRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> SourceVersionRecord:
        """Register a new immutable version; registering resets verification."""
        content_sha = _digest(request.content)
        chunks = _chunk_content(request.source_key, request.version_label, request.content)
        with self._transaction() as connection:
            self._require_workspace_actor(
                connection, organization_id, actor_user_id, request.workspace_id
            )
            vault_policy = self._vault_policy(
                connection, organization_id, request.workspace_id
            )
            self._enforce_vault_registration(
                request, vault_policy=vault_policy, actor_user_id=actor_user_id
            )
            source = connection.execute(
                """
                SELECT source_id, workspace_id, source_type, classification
                FROM sources.sources
                WHERE organization_id = %s AND source_key = %s
                FOR UPDATE
                """,
                (organization_id, request.source_key),
            ).fetchone()
            if source is None:
                source = connection.execute(
                    """
                    INSERT INTO sources.sources (
                        organization_id, workspace_id, source_key, name, source_type,
                        classification, access_mode, owner_user_id, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'READ_ONLY', %s, 'SOURCE_RECEIVED')
                    RETURNING source_id, workspace_id, source_type, classification
                    """,
                    (
                        organization_id,
                        request.workspace_id,
                        request.source_key,
                        request.name,
                        request.source_type,
                        request.classification,
                        actor_user_id,
                    ),
                ).fetchone()
            else:
                if source["workspace_id"] != request.workspace_id:
                    raise SourceConflictError("a source cannot move between workspaces")
                if source["source_type"] != request.source_type:
                    raise SourceConflictError("a source type is immutable")
                if source["classification"] != request.classification:
                    raise SourceConflictError("a source classification is immutable")
                connection.execute(
                    """
                    UPDATE sources.sources
                    SET name = %s, status = 'SOURCE_RECEIVED'
                    WHERE source_id = %s
                    """,
                    (request.name, source["source_id"]),
                )
            if source is None:
                raise SourceRegistryError("source could not be registered")
            try:
                version = connection.execute(
                    """
                    INSERT INTO sources.versions (
                        source_id, version_label, sha256, locator, source_vault_policy_id,
                        vault_attested_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING source_version_id
                    """,
                    (
                        source["source_id"],
                        request.version_label,
                        content_sha,
                        request.locator,
                        request.source_vault_policy_id,
                        actor_user_id if request.vault_attestation else None,
                    ),
                ).fetchone()
            except UniqueViolation as error:
                raise SourceConflictError("source version label already exists") from error
            if version is None:
                raise SourceRegistryError("source version could not be registered")
            for index, citation_key, anchor, text in chunks:
                connection.execute(
                    """
                    INSERT INTO sources.content_chunks (
                        source_version_id, chunk_index, citation_key, anchor,
                        content_text, content_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        version["source_version_id"],
                        index,
                        citation_key,
                        anchor,
                        text,
                        _digest(text),
                    ),
                )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="SOURCE_VERSION_REGISTERED",
                entity_type="SOURCE_VERSION",
                entity_id=version["source_version_id"],
                correlation_id=correlation_id,
                reason="Human registered a read-only source version",
                metadata={
                    "source_key": request.source_key,
                    "version_label": request.version_label,
                    "sha256": content_sha,
                    "citation_count": len(chunks),
                    "source_vault_policy_id": str(request.source_vault_policy_id)
                    if request.source_vault_policy_id is not None
                    else None,
                },
            )
            return SourceVersionRecord(
                source_id=source["source_id"],
                source_version_id=version["source_version_id"],
                workspace_id=request.workspace_id,
                source_key=request.source_key,
                name=request.name,
                source_type=request.source_type,
                classification=request.classification,
                status="SOURCE_RECEIVED",
                version_label=request.version_label,
                sha256=content_sha,
                locator=request.locator,
                citation_count=len(chunks),
                source_vault_policy_id=request.source_vault_policy_id,
            )

    def verify(
        self,
        workspace_id: UUID,
        source_key: str,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        reason: str,
    ) -> SourceVersionRecord:
        """Make all current versions of the source eligible for read-only retrieval."""
        with self._transaction() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            source = self._source_for_workspace(
                connection, organization_id, workspace_id, source_key, lock=True
            )
            if source["status"] == "RETIRED":
                raise SourceConflictError("a retired source cannot be verified")
            version = connection.execute(
                """
                SELECT version.source_version_id, version.version_label, version.sha256,
                       version.locator, version.source_vault_policy_id,
                       count(chunk.source_chunk_id) AS citation_count
                FROM sources.versions AS version
                LEFT JOIN sources.content_chunks AS chunk
                  ON chunk.source_version_id = version.source_version_id
                WHERE version.source_id = %s
                GROUP BY version.source_version_id
                ORDER BY version.received_at DESC, version.source_version_id DESC
                LIMIT 1
                """,
                (source["source_id"],),
            ).fetchone()
            if version is None:
                raise SourceRegistryError("source does not have a version")
            connection.execute(
                "UPDATE sources.sources SET status = 'VERIFIED' WHERE source_id = %s",
                (source["source_id"],),
            )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="SOURCE_VERIFIED",
                entity_type="SOURCE_VERSION",
                entity_id=version["source_version_id"],
                correlation_id=correlation_id,
                reason=reason,
                metadata={"source_key": source_key, "version_label": version["version_label"]},
            )
            return SourceVersionRecord(
                source_id=source["source_id"],
                source_version_id=version["source_version_id"],
                workspace_id=workspace_id,
                source_key=source_key,
                name=source["name"],
                source_type=source["source_type"],
                classification=source["classification"],
                status="VERIFIED",
                version_label=version["version_label"],
                sha256=version["sha256"],
                locator=version["locator"],
                citation_count=version["citation_count"],
                source_vault_policy_id=version["source_vault_policy_id"],
            )

    def configure_vault_policy(
        self,
        workspace_id: UUID,
        request: SourceVaultPolicyRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> SourceVaultPolicyRecord:
        """Persist a read-only human boundary for sources used in the H5 pilot."""
        allowed_folder_id = _google_drive_folder_id(request.allowed_root_url)
        excluded_folder_id = _google_drive_folder_id(request.excluded_folder_url)
        if allowed_folder_id is None or excluded_folder_id is None:
            raise SourceRegistryError("Google Drive folder policy could not be parsed")
        with self._transaction() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            row = connection.execute(
                """
                INSERT INTO sources.vault_policies (
                    organization_id, workspace_id, allowed_root_url, allowed_root_folder_id,
                    excluded_folder_url, excluded_folder_id, created_by_user_id, updated_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (organization_id, workspace_id) DO UPDATE
                SET allowed_root_url = EXCLUDED.allowed_root_url,
                    allowed_root_folder_id = EXCLUDED.allowed_root_folder_id,
                    excluded_folder_url = EXCLUDED.excluded_folder_url,
                    excluded_folder_id = EXCLUDED.excluded_folder_id,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = now()
                RETURNING source_vault_policy_id, workspace_id, allowed_root_url,
                          excluded_folder_url, access_mode, created_at, updated_at
                """,
                (
                    organization_id,
                    workspace_id,
                    request.allowed_root_url,
                    allowed_folder_id,
                    request.excluded_folder_url,
                    excluded_folder_id,
                    actor_user_id,
                    actor_user_id,
                ),
            ).fetchone()
            if row is None:
                raise SourceRegistryError("Source Vault policy could not be saved")
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="SOURCE_VAULT_CONFIGURED",
                entity_type="SOURCE_VAULT_POLICY",
                entity_id=row["source_vault_policy_id"],
                correlation_id=correlation_id,
                reason=request.reason,
                metadata={
                    "workspace_id": str(workspace_id),
                    "access_mode": "READ_ONLY",
                    "allowed_root_folder_id": allowed_folder_id,
                    "excluded_folder_id": excluded_folder_id,
                },
            )
            return SourceVaultPolicyRecord(**row)

    def get_vault_policy(
        self, workspace_id: UUID, *, organization_id: UUID
    ) -> SourceVaultPolicyRecord | None:
        with self._connection() as connection:
            row = self._vault_policy(connection, organization_id, workspace_id)
        if row is None:
            return None
        return SourceVaultPolicyRecord(
            source_vault_policy_id=row["source_vault_policy_id"],
            workspace_id=row["workspace_id"],
            allowed_root_url=row["allowed_root_url"],
            excluded_folder_url=row["excluded_folder_url"],
            access_mode=row["access_mode"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_source_versions(
        self, workspace_id: UUID, *, organization_id: UUID
    ) -> list[SourceVersionRecord]:
        """List the newest immutable version for each workspace source."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (source.source_id)
                       source.source_id, version.source_version_id, source.workspace_id,
                       source.source_key, source.name, source.source_type, source.classification,
                       source.status, version.version_label, version.sha256, version.locator,
                       version.source_vault_policy_id,
                       count(chunk.source_chunk_id) OVER (PARTITION BY version.source_version_id)
                         AS citation_count
                FROM sources.sources AS source
                JOIN sources.versions AS version ON version.source_id = source.source_id
                LEFT JOIN sources.content_chunks AS chunk
                  ON chunk.source_version_id = version.source_version_id
                WHERE source.organization_id = %s AND source.workspace_id = %s
                ORDER BY source.source_id, version.received_at DESC, version.source_version_id DESC
                """,
                (organization_id, workspace_id),
            ).fetchall()
        return [SourceVersionRecord(**row) for row in rows]

    def search_evidence(
        self,
        workspace_id: UUID,
        query: str,
        *,
        organization_id: UUID,
        limit: int = 12,
    ) -> list[EvidenceCitation]:
        """Return only verified, workspace-scoped evidence with stable citations."""
        if limit < 1 or limit > 50:
            raise ValueError("source evidence limit must be between 1 and 50")
        normalized = query.strip()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT chunk.citation_key, source.source_key, version.version_label,
                       version.locator,
                       chunk.anchor, chunk.content_text
                FROM sources.sources AS source
                JOIN sources.versions AS version ON version.source_id = source.source_id
                JOIN sources.content_chunks AS chunk
                  ON chunk.source_version_id = version.source_version_id
                WHERE source.organization_id = %s AND source.workspace_id = %s
                  AND source.status = 'VERIFIED'
                  AND (%s = '' OR chunk.content_text ILIKE ('%%' || %s || '%%'))
                ORDER BY version.received_at DESC, chunk.chunk_index ASC
                LIMIT %s
                """,
                (organization_id, workspace_id, normalized, normalized, limit),
            ).fetchall()
        return [
            EvidenceCitation(
                citation_key=row["citation_key"],
                source_key=row["source_key"],
                version_label=row["version_label"],
                locator=row["locator"],
                anchor=row["anchor"],
                excerpt=_excerpt(row["content_text"]),
            )
            for row in rows
        ]

    @staticmethod
    def _source_for_workspace(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        source_key: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        source = connection.execute(
            f"""
            SELECT source_id, name, source_type, classification, status
            FROM sources.sources
            WHERE organization_id = %s AND workspace_id = %s AND source_key = %s{suffix}
            """,
            (organization_id, workspace_id, source_key),
        ).fetchone()
        if source is None:
            raise SourceNotFoundError("source was not found in this workspace")
        return dict(source)

    @staticmethod
    def _vault_policy(
        connection: psycopg.Connection[Any], organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT source_vault_policy_id, workspace_id, allowed_root_url, allowed_root_folder_id,
                   excluded_folder_url, excluded_folder_id, access_mode, created_at, updated_at
            FROM sources.vault_policies
            WHERE organization_id = %s AND workspace_id = %s
            """,
            (organization_id, workspace_id),
        ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _enforce_vault_registration(
        request: SourceRegistrationRequest,
        *,
        vault_policy: dict[str, Any] | None,
        actor_user_id: UUID,
    ) -> None:
        del actor_user_id  # Attestation identity is persisted by the caller transaction.
        if vault_policy is None:
            if request.source_vault_policy_id is not None or request.vault_attestation:
                raise SourceConflictError(
                    "Source Vault policy is not configured for this workspace"
                )
            return
        if request.source_vault_policy_id != vault_policy["source_vault_policy_id"]:
            raise SourceConflictError(
                "source registration must reference the current Source Vault policy"
            )
        if not request.vault_attestation:
            raise SourceConflictError(
                "source registration requires explicit Source Vault attestation"
            )
        if not request.locator:
            raise SourceConflictError(
                "a Source Vault registration requires a declared source locator"
            )
        if vault_policy["excluded_folder_id"] in request.locator:
            raise SourceConflictError(
                "the declared source locator is explicitly excluded by Source Vault"
            )

    @staticmethod
    def _require_workspace_actor(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        membership = connection.execute(
            """
            SELECT 1
            FROM identity.users AS actor
            JOIN workspace.memberships AS membership ON membership.user_id = actor.user_id
            JOIN workspace.workspaces AS workspace
              ON workspace.workspace_id = membership.workspace_id
            WHERE actor.organization_id = %s AND actor.user_id = %s
              AND workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE'
            """,
            (organization_id, actor_user_id, workspace_id, organization_id),
        ).fetchone()
        if membership is None:
            raise SourceRegistryError("active workspace membership is required")

    @staticmethod
    def _append_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
                action,
                entity_type,
                entity_id,
                correlation_id,
                reason,
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


def _chunk_content(
    source_key: str, version_label: str, content: str
) -> list[tuple[int, str, str, str]]:
    """Produce bounded line-based citations without a model or parser."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        lines = [content.strip()]
    chunks: list[tuple[int, str, str, str]] = []
    group_size = 8
    for chunk_index, start in enumerate(range(0, len(lines), group_size)):
        end = min(start + group_size, len(lines))
        text = "\n".join(lines[start:end])
        citation_key = f"{source_key}@{version_label}#L{start + 1}-L{end}"
        chunks.append((chunk_index, citation_key, f"lines {start + 1}-{end}", text))
    return chunks


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _excerpt(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:800]


def _google_drive_folder_id(value: str) -> str | None:
    """Extract a folder id without calling Google Drive or following a URL."""
    match = _GOOGLE_DRIVE_FOLDER_URL.match(value.strip())
    return match.group(1) if match is not None else None

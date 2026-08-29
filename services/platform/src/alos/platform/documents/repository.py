from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.persistence.database import PostgresOperationalStore
from alos.platform import StoredDocumentView
from alos.platform.documents.storage import StoredObject
from alos.security import Principal
from alos.security.authorization import AuthorizationDenied


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    document_id: UUID
    document_version_id: UUID
    organization_id: UUID
    division_code: str | None
    project_id: UUID | None
    logical_name: str
    classification: str
    version_number: int
    original_filename: str | None
    object_key: str
    sha256: str
    media_type: str
    size_bytes: int
    storage_provider: str
    bucket_name: str | None
    storage_etag: str | None
    scan_status: str
    verification_status: str
    created_at: datetime


class PostgresDocumentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        division_code: str | None,
        project_id: UUID | None,
        logical_name: str,
        classification: str,
        original_filename: str,
        sha256: str,
        media_type: str,
        size_bytes: int,
        stored: StoredObject,
        scan_status: str,
        principal: Principal,
    ) -> StoredDocumentView:
        with self._engine.begin() as connection:
            division_id = self._division_id(connection, division_code, principal)
            self._assert_project(connection, project_id, principal)
            created_at = connection.execute(
                text(
                    """
                    INSERT INTO platform.documents
                        (document_id, organization_id, division_id, project_id, logical_name,
                         classification, created_at, created_by, updated_at)
                    VALUES
                        (:document_id, :organization_id, :division_id, :project_id,
                         :logical_name, :classification, now(),
                         (SELECT user_id FROM identity.users
                          WHERE user_id = :actor_id AND organization_id = :organization_id),
                         now())
                    RETURNING created_at
                    """
                ),
                {
                    "document_id": document_id,
                    "organization_id": principal.organization_id,
                    "division_id": division_id,
                    "project_id": project_id,
                    "logical_name": logical_name,
                    "classification": classification,
                    "actor_id": principal.user_id,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO platform.document_versions
                        (document_version_id, document_id, version_number, original_filename,
                         object_key, sha256, media_type, size_bytes, storage_provider,
                         bucket_name, storage_etag, scan_status, verification_status,
                         created_at, created_by)
                    VALUES
                        (:version_id, :document_id, 1, :original_filename, :object_key,
                         :sha256, :media_type, :size_bytes, :storage_provider, :bucket_name,
                         :storage_etag, :scan_status, 'UNVERIFIED', :created_at,
                         (SELECT user_id FROM identity.users
                          WHERE user_id = :actor_id AND organization_id = :organization_id))
                    """
                ),
                {
                    "version_id": version_id,
                    "document_id": document_id,
                    "original_filename": original_filename,
                    "object_key": stored.object_key,
                    "sha256": sha256,
                    "media_type": media_type,
                    "size_bytes": size_bytes,
                    "storage_provider": stored.provider,
                    "bucket_name": stored.bucket,
                    "storage_etag": stored.etag,
                    "scan_status": scan_status,
                    "created_at": created_at,
                    "actor_id": principal.user_id,
                    "organization_id": principal.organization_id,
                },
            )
            result = StoredDocumentView(
                document_id=document_id,
                document_version_id=version_id,
                organization_id=principal.organization_id,
                division_code=division_code,
                project_id=project_id,
                logical_name=logical_name,
                classification=classification,
                version_number=1,
                original_filename=original_filename,
                sha256=sha256,
                media_type=media_type,
                size_bytes=size_bytes,
                storage_provider=stored.provider,
                scan_status=scan_status,
                verification_status="UNVERIFIED",
                created_at=created_at,
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "document.uploaded",
                "document",
                document_id,
                uuid4(),
                None,
                {
                    "document_version_id": str(version_id),
                    "division_code": division_code,
                    "project_id": str(project_id) if project_id else None,
                    "classification": classification,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "storage_provider": stored.provider,
                    "scan_status": scan_status,
                },
            )
        return result

    def append_version(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        original_filename: str,
        sha256: str,
        media_type: str,
        size_bytes: int,
        stored: StoredObject,
        scan_status: str,
        principal: Principal,
    ) -> StoredDocumentView:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT d.organization_id, d.project_id, d.logical_name,
                               d.classification, div.code AS division_code
                        FROM platform.documents d
                        LEFT JOIN identity.divisions div ON div.division_id = d.division_id
                        WHERE d.document_id = :document_id
                          AND d.organization_id = :organization_id
                        FOR UPDATE OF d
                        """
                    ),
                    {
                        "document_id": document_id,
                        "organization_id": principal.organization_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Dokumen tidak ditemukan")
            version_number = connection.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM platform.document_versions
                    WHERE document_id = :document_id
                    """
                ),
                {"document_id": document_id},
            ).scalar_one()
            created_at = connection.execute(
                text(
                    """
                    INSERT INTO platform.document_versions
                        (document_version_id, document_id, version_number, original_filename,
                         object_key, sha256, media_type, size_bytes, storage_provider,
                         bucket_name, storage_etag, scan_status, verification_status,
                         created_at, created_by)
                    VALUES
                        (:version_id, :document_id, :version_number, :original_filename,
                         :object_key, :sha256, :media_type, :size_bytes, :storage_provider,
                         :bucket_name, :storage_etag, :scan_status, 'UNVERIFIED', now(),
                         (SELECT user_id FROM identity.users
                          WHERE user_id = :actor_id AND organization_id = :organization_id))
                    RETURNING created_at
                    """
                ),
                {
                    "version_id": version_id,
                    "document_id": document_id,
                    "version_number": version_number,
                    "original_filename": original_filename,
                    "object_key": stored.object_key,
                    "sha256": sha256,
                    "media_type": media_type,
                    "size_bytes": size_bytes,
                    "storage_provider": stored.provider,
                    "bucket_name": stored.bucket,
                    "storage_etag": stored.etag,
                    "scan_status": scan_status,
                    "actor_id": principal.user_id,
                    "organization_id": principal.organization_id,
                },
            ).scalar_one()
            connection.execute(
                text("UPDATE platform.documents SET updated_at = now() WHERE document_id = :id"),
                {"id": document_id},
            )
            result = StoredDocumentView(
                document_id=document_id,
                document_version_id=version_id,
                organization_id=row["organization_id"],
                division_code=row["division_code"],
                project_id=row["project_id"],
                logical_name=row["logical_name"],
                classification=row["classification"],
                version_number=version_number,
                original_filename=original_filename,
                sha256=sha256,
                media_type=media_type,
                size_bytes=size_bytes,
                storage_provider=stored.provider,
                scan_status=scan_status,
                verification_status="UNVERIFIED",
                created_at=created_at,
            )
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "document.version_uploaded",
                "document",
                document_id,
                uuid4(),
                {"previous_version": version_number - 1},
                {
                    "document_version_id": str(version_id),
                    "version_number": version_number,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "scan_status": scan_status,
                },
            )
        return result

    def get(
        self,
        document_id: UUID,
        principal: Principal,
        version_number: int | None = None,
    ) -> DocumentRecord:
        parameters: dict[str, Any] = {
            "document_id": document_id,
            "organization_id": principal.organization_id,
            "version_number": version_number,
        }
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT d.document_id, dv.document_version_id, d.organization_id,
                               div.code AS division_code, d.project_id, d.logical_name,
                               d.classification, dv.version_number, dv.original_filename,
                               dv.object_key, dv.sha256, dv.media_type, dv.size_bytes,
                               dv.storage_provider, dv.bucket_name, dv.storage_etag,
                               dv.scan_status, dv.verification_status, dv.created_at
                        FROM platform.documents d
                        LEFT JOIN identity.divisions div ON div.division_id = d.division_id
                        JOIN platform.document_versions dv ON dv.document_id = d.document_id
                        WHERE d.document_id = :document_id
                          AND d.organization_id = :organization_id
                          AND (
                              CAST(:version_number AS integer) IS NULL
                              OR dv.version_number = CAST(:version_number AS integer)
                          )
                        ORDER BY dv.version_number DESC
                        LIMIT 1
                        """
                    ),
                    parameters,
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError("Dokumen atau versinya tidak ditemukan")
        return DocumentRecord(**row)

    def record_download(self, record: DocumentRecord, principal: Principal) -> None:
        with self._engine.begin() as connection:
            PostgresOperationalStore._append_audit(
                connection,
                principal,
                "document.downloaded",
                "document",
                record.document_id,
                uuid4(),
                None,
                {
                    "document_version_id": str(record.document_version_id),
                    "version_number": record.version_number,
                    "sha256": record.sha256,
                },
            )

    @staticmethod
    def _division_id(
        connection: Any, division_code: str | None, principal: Principal
    ) -> UUID | None:
        if division_code is None:
            return None
        division_id = connection.execute(
            text(
                """
                SELECT division_id FROM identity.divisions
                WHERE organization_id = :organization_id AND code = :division_code
                """
            ),
            {
                "organization_id": principal.organization_id,
                "division_code": division_code,
            },
        ).scalar_one_or_none()
        if division_id is None:
            raise KeyError("Divisi dokumen tidak ditemukan")
        return division_id

    @staticmethod
    def _assert_project(connection: Any, project_id: UUID | None, principal: Principal) -> None:
        if project_id is None:
            return
        exists = connection.execute(
            text(
                """
                SELECT 1 FROM platform.projects
                WHERE project_id = :project_id AND organization_id = :organization_id
                """
            ),
            {"project_id": project_id, "organization_id": principal.organization_id},
        ).scalar_one_or_none()
        if exists is None:
            raise KeyError("Proyek dokumen tidak ditemukan")
        if not principal.can_access_project(project_id):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke proyek dokumen")

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alos.platform.documents.repository import DocumentRecord
from alos.platform.documents.service import DocumentService, inspect_upload
from alos.platform.documents.storage import (
    FilesystemObjectStorage,
    ObjectStorageError,
)
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied
from alos.security.request_limits import RequestBodyLimitMiddleware


def test_filesystem_storage_round_trip_and_delete(tmp_path) -> None:
    storage = FilesystemObjectStorage(tmp_path, "alos-documents")
    payload = b"%PDF-1.7\nsynthetic-test"

    result = storage.put(
        "organization/shared/document/version.pdf",
        BytesIO(payload),
        size_bytes=len(payload),
        media_type="application/pdf",
        metadata={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert result.provider == "FILESYSTEM"
    with storage.open(result.object_key) as stored:
        assert stored.read() == payload
    with pytest.raises(ObjectStorageError):
        storage.put(
            result.object_key,
            BytesIO(b"replacement"),
            size_bytes=11,
            media_type="application/pdf",
            metadata={},
        )
    with storage.open(result.object_key) as stored:
        assert stored.read() == payload
    storage.delete(result.object_key)
    with pytest.raises(ObjectStorageError):
        storage.open(result.object_key)


def test_filesystem_storage_rejects_path_traversal(tmp_path) -> None:
    storage = FilesystemObjectStorage(tmp_path, "alos-documents")

    with pytest.raises(ObjectStorageError, match="Object key tidak valid"):
        storage.put(
            "../outside.pdf",
            BytesIO(b"%PDF-1.7"),
            size_bytes=8,
            media_type="application/pdf",
            metadata={},
        )


def test_document_inspection_computes_server_side_metadata() -> None:
    payload = b"%PDF-1.7\nsynthetic-test"

    result = inspect_upload(
        BytesIO(payload),
        filename="../../Bukti Pembayaran.PDF",
        declared_media_type="application/pdf",
        max_upload_bytes=1024,
    )

    assert result.original_filename == "Bukti Pembayaran.PDF"
    assert result.extension == ".pdf"
    assert result.media_type == "application/pdf"
    assert result.size_bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("payload", "filename", "media_type", "message"),
    [
        (b"not-a-pdf", "bukti.pdf", "application/pdf", "bukan PDF"),
        (b"%PDF-1.7", "bukti.exe", "application/octet-stream", "tidak didukung"),
        (b"%PDF-1.7", "bukti.pdf", "image/png", "tidak sesuai"),
        (b"", "bukti.pdf", "application/pdf", "Berkas kosong"),
    ],
)
def test_document_inspection_rejects_unsafe_content(
    payload: bytes,
    filename: str,
    media_type: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        inspect_upload(
            BytesIO(payload),
            filename=filename,
            declared_media_type=media_type,
            max_upload_bytes=1024,
        )


def test_document_inspection_enforces_size_limit() -> None:
    with pytest.raises(ValueError, match="melebihi batas"):
        inspect_upload(
            BytesIO(b"%PDF-1.7\nlarge"),
            filename="large.pdf",
            declared_media_type="application/pdf",
            max_upload_bytes=8,
        )


def test_text_validation_checks_the_entire_file() -> None:
    payload = b"a" * 9000 + b"\xff"

    with pytest.raises(ValueError, match="UTF-8"):
        inspect_upload(
            BytesIO(payload),
            filename="data.txt",
            declared_media_type="text/plain",
            max_upload_bytes=20_000,
        )


def test_pending_malware_scan_blocks_download() -> None:
    organization_id, project_id, document_id = uuid4(), uuid4(), uuid4()
    record = DocumentRecord(
        document_id=document_id,
        document_version_id=uuid4(),
        organization_id=organization_id,
        division_code="FINANCE",
        project_id=project_id,
        logical_name="Bukti Sintetis",
        classification="INTERNAL",
        version_number=1,
        original_filename="bukti.pdf",
        object_key="organization/project/document/version.pdf",
        sha256="a" * 64,
        media_type="application/pdf",
        size_bytes=8,
        storage_provider="FILESYSTEM",
        bucket_name="alos-documents",
        storage_etag=None,
        scan_status="PENDING",
        verification_status="UNVERIFIED",
        created_at=datetime.now(UTC),
    )
    principal = Principal(
        user_id=uuid4(),
        organization_id=organization_id,
        roles=frozenset({Role.FINANCE}),
        division_codes=frozenset({"FINANCE"}),
        project_ids=frozenset({project_id}),
    )
    repository = _PendingDocumentRepository(record)
    storage = _GuardedStorage()
    service = DocumentService(
        repository,  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        max_upload_bytes=1024,
        scan_mode="external",
    )

    with pytest.raises(ValueError, match="pemeriksaan malware"):
        service.download(document_id, principal)

    assert storage.was_opened is False


def test_shared_confidential_document_blocks_business_role() -> None:
    organization_id, project_id, document_id = uuid4(), uuid4(), uuid4()
    record = _document_record(
        organization_id=organization_id,
        project_id=project_id,
        document_id=document_id,
        division_code=None,
        classification="CONFIDENTIAL",
        scan_status="NOT_CONFIGURED",
    )
    principal = Principal(
        user_id=uuid4(),
        organization_id=organization_id,
        roles=frozenset({Role.FINANCE}),
        division_codes=frozenset({"FINANCE"}),
        project_ids=frozenset({project_id}),
    )
    storage = _GuardedStorage()
    service = DocumentService(
        _PendingDocumentRepository(record),  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        max_upload_bytes=1024,
        scan_mode="disabled",
    )

    with pytest.raises(AuthorizationDenied, match="tingkat organisasi"):
        service.download(document_id, principal)

    assert storage.was_opened is False


def test_request_body_limit_rejects_oversized_content_length() -> None:
    application = FastAPI()
    application.add_middleware(RequestBodyLimitMiddleware, max_bytes=8)

    @application.post("/payload")
    def payload() -> dict[str, bool]:
        return {"accepted": True}

    response = TestClient(application).post("/payload", content=b"123456789")

    assert response.status_code == 413
    assert response.json()["detail"] == "Ukuran request melebihi batas layanan"


def _document_record(
    *,
    organization_id,
    project_id,
    document_id,
    division_code,
    classification,
    scan_status,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        document_version_id=uuid4(),
        organization_id=organization_id,
        division_code=division_code,
        project_id=project_id,
        logical_name="Bukti Sintetis",
        classification=classification,
        version_number=1,
        original_filename="bukti.pdf",
        object_key="organization/project/document/version.pdf",
        sha256="a" * 64,
        media_type="application/pdf",
        size_bytes=8,
        storage_provider="FILESYSTEM",
        bucket_name="alos-documents",
        storage_etag=None,
        scan_status=scan_status,
        verification_status="UNVERIFIED",
        created_at=datetime.now(UTC),
    )


class _PendingDocumentRepository:
    def __init__(self, record: DocumentRecord) -> None:
        self._record = record

    def get(
        self,
        document_id,
        principal,
        version_number=None,
    ) -> DocumentRecord:
        del document_id, principal, version_number
        return self._record


class _GuardedStorage:
    provider_name = "FILESYSTEM"
    bucket_name = "alos-documents"

    def __init__(self) -> None:
        self.was_opened = False

    def open(self, object_key):
        del object_key
        self.was_opened = True
        return BytesIO(b"%PDF-1.7")

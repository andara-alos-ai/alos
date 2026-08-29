from collections.abc import Iterator
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.entrypoints.api import PrincipalDependency, SettingsDependency, database_for_url
from alos.platform import StoredDocumentView
from alos.platform.documents import (
    DocumentService,
    ObjectStorage,
    ObjectStorageError,
    PostgresDocumentRepository,
    object_storage_for,
)
from alos.security.authorization import AuthorizationDenied

router = APIRouter()


def document_repository(settings: SettingsDependency) -> PostgresDocumentRepository:
    return PostgresDocumentRepository(database_for_url(settings.database_url).engine)


def document_storage(settings: SettingsDependency) -> ObjectStorage:
    return object_storage_for(settings)


DocumentRepositoryDependency = Annotated[
    PostgresDocumentRepository, Depends(document_repository)
]
DocumentStorageDependency = Annotated[ObjectStorage, Depends(document_storage)]


def document_service(
    settings: SettingsDependency,
    repository: DocumentRepositoryDependency,
    storage: DocumentStorageDependency,
) -> DocumentService:
    return DocumentService(
        repository,
        storage,
        max_upload_bytes=settings.object_storage_max_upload_bytes,
        scan_mode=settings.document_scan_mode,
    )


DocumentServiceDependency = Annotated[DocumentService, Depends(document_service)]


@router.post(
    "/documents/upload",
    response_model=StoredDocumentView,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_document(
    file: Annotated[UploadFile, File(description="Berkas dokumen atau evidence")],
    logical_name: Annotated[str, Form(min_length=2, max_length=160)],
    classification: Annotated[
        Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"], Form()
    ],
    principal: PrincipalDependency,
    service: DocumentServiceDependency,
    division_code: Annotated[
        str | None, Form(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    ] = None,
    project_id: Annotated[UUID | None, Form()] = None,
) -> StoredDocumentView:
    try:
        return service.upload(
            file.file,
            filename=file.filename,
            declared_media_type=file.content_type,
            logical_name=logical_name,
            classification=classification,
            division_code=division_code,
            project_id=project_id,
            principal=principal,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Dokumen atau hash sudah digunakan") from exc
    except ObjectStorageError as exc:
        raise HTTPException(status_code=503, detail="Penyimpanan dokumen belum tersedia") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.post(
    "/documents/{document_id}/versions",
    response_model=StoredDocumentView,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_document_version(
    document_id: UUID,
    file: Annotated[UploadFile, File(description="Berkas versi baru")],
    principal: PrincipalDependency,
    service: DocumentServiceDependency,
) -> StoredDocumentView:
    try:
        return service.upload_version(
            document_id,
            file.file,
            filename=file.filename,
            declared_media_type=file.content_type,
            principal=principal,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Versi atau hash sudah digunakan") from exc
    except ObjectStorageError as exc:
        raise HTTPException(status_code=503, detail="Penyimpanan dokumen belum tersedia") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc


@router.get("/documents/{document_id}/content", tags=["documents"])
def download_document(
    document_id: UUID,
    principal: PrincipalDependency,
    service: DocumentServiceDependency,
    version_number: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    try:
        download = service.download(
            document_id,
            principal,
            version_number=version_number,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ObjectStorageError as exc:
        raise HTTPException(status_code=503, detail="Berkas dokumen belum tersedia") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc

    def content() -> Iterator[bytes]:
        try:
            while chunk := download.stream.read(1024 * 1024):
                yield chunk
        finally:
            download.stream.close()

    filename = download.record.original_filename or f"document-{document_id}"
    encoded_filename = quote(filename, safe="")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Length": str(download.record.size_bytes),
        "X-Content-SHA256": download.record.sha256,
        "X-Document-Version": str(download.record.version_number),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(content(), media_type=download.record.media_type, headers=headers)

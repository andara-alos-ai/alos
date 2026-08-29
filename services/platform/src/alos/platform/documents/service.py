from __future__ import annotations

import codecs
import hashlib
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO, Literal
from uuid import UUID, uuid4

from alos.platform import StoredDocumentView
from alos.platform.documents.repository import DocumentRecord, PostgresDocumentRepository
from alos.platform.documents.storage import ObjectStorage, ReadableStream
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied

DocumentClassification = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
logger = logging.getLogger(__name__)

_MEDIA_TYPES: dict[str, tuple[str, frozenset[str]]] = {
    ".pdf": ("application/pdf", frozenset({"application/pdf", "application/octet-stream"})),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset(
            {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/zip",
                "application/octet-stream",
            }
        ),
    ),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        frozenset(
            {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/zip",
                "application/octet-stream",
            }
        ),
    ),
    ".csv": ("text/csv", frozenset({"text/csv", "text/plain", "application/octet-stream"})),
    ".txt": ("text/plain", frozenset({"text/plain", "application/octet-stream"})),
    ".png": ("image/png", frozenset({"image/png", "application/octet-stream"})),
    ".jpg": (
        "image/jpeg",
        frozenset({"image/jpeg", "image/jpg", "application/octet-stream"}),
    ),
    ".jpeg": (
        "image/jpeg",
        frozenset({"image/jpeg", "image/jpg", "application/octet-stream"}),
    ),
}

_UPLOAD_ROLES = frozenset(
    {
        Role.DIRECTOR,
        Role.DIVISION_HEAD,
        Role.SALES,
        Role.FINANCE,
        Role.PROPERTY,
        Role.HR,
        Role.LEGAL,
        Role.IT_ADMIN,
    }
)
_READ_ROLES = _UPLOAD_ROLES | {Role.AI_EXECUTIVE, Role.AUDITOR}


@dataclass(frozen=True, slots=True)
class InspectedUpload:
    original_filename: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(slots=True)
class DocumentDownload:
    record: DocumentRecord
    stream: ReadableStream


class DocumentService:
    def __init__(
        self,
        repository: PostgresDocumentRepository,
        storage: ObjectStorage,
        *,
        max_upload_bytes: int,
        scan_mode: str,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes
        self._scan_mode = scan_mode

    def upload(
        self,
        stream: BinaryIO,
        *,
        filename: str | None,
        declared_media_type: str | None,
        logical_name: str,
        classification: DocumentClassification,
        division_code: str | None,
        project_id: UUID | None,
        principal: Principal,
    ) -> StoredDocumentView:
        self._require_upload_role(principal)
        normalized_logical_name = logical_name.strip()
        if len(normalized_logical_name) < 2:
            raise ValueError("Nama logis dokumen wajib minimal dua karakter")
        if project_id is not None and not principal.can_access_project(project_id):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke proyek dokumen")
        owner_division = self._resolve_upload_division(division_code, principal)
        inspected = inspect_upload(
            stream,
            filename=filename,
            declared_media_type=declared_media_type,
            max_upload_bytes=self._max_upload_bytes,
        )
        document_id, version_id = uuid4(), uuid4()
        object_key = self._object_key(
            principal.organization_id,
            project_id,
            document_id,
            version_id,
            inspected.extension,
        )
        stored = self._storage.put(
            object_key,
            stream,
            size_bytes=inspected.size_bytes,
            media_type=inspected.media_type,
            metadata={
                "document-id": str(document_id),
                "document-version-id": str(version_id),
                "sha256": inspected.sha256,
            },
        )
        try:
            return self._repository.create(
                document_id=document_id,
                version_id=version_id,
                division_code=owner_division,
                project_id=project_id,
                logical_name=normalized_logical_name,
                classification=classification,
                original_filename=inspected.original_filename,
                sha256=inspected.sha256,
                media_type=inspected.media_type,
                size_bytes=inspected.size_bytes,
                stored=stored,
                scan_status=self._initial_scan_status,
                principal=principal,
            )
        except Exception:
            self._best_effort_delete(object_key)
            raise

    def upload_version(
        self,
        document_id: UUID,
        stream: BinaryIO,
        *,
        filename: str | None,
        declared_media_type: str | None,
        principal: Principal,
    ) -> StoredDocumentView:
        self._require_upload_role(principal)
        record = self._repository.get(document_id, principal)
        self._authorize_version_upload(record, principal)
        inspected = inspect_upload(
            stream,
            filename=filename,
            declared_media_type=declared_media_type,
            max_upload_bytes=self._max_upload_bytes,
        )
        version_id = uuid4()
        object_key = self._object_key(
            principal.organization_id,
            record.project_id,
            document_id,
            version_id,
            inspected.extension,
        )
        stored = self._storage.put(
            object_key,
            stream,
            size_bytes=inspected.size_bytes,
            media_type=inspected.media_type,
            metadata={
                "document-id": str(document_id),
                "document-version-id": str(version_id),
                "sha256": inspected.sha256,
            },
        )
        try:
            return self._repository.append_version(
                document_id=document_id,
                version_id=version_id,
                original_filename=inspected.original_filename,
                sha256=inspected.sha256,
                media_type=inspected.media_type,
                size_bytes=inspected.size_bytes,
                stored=stored,
                scan_status=self._initial_scan_status,
                principal=principal,
            )
        except Exception:
            self._best_effort_delete(object_key)
            raise

    def download(
        self,
        document_id: UUID,
        principal: Principal,
        *,
        version_number: int | None = None,
    ) -> DocumentDownload:
        if not principal.roles.intersection(_READ_ROLES):
            raise AuthorizationDenied("Role tidak diizinkan membaca dokumen")
        record = self._repository.get(document_id, principal, version_number)
        self._authorize_download(record, principal)
        if record.storage_provider == "EXTERNAL_REFERENCE" or record.bucket_name is None:
            raise ValueError(
                "Dokumen lama hanya memiliki metadata dan belum memiliki berkas tersimpan"
            )
        if record.storage_provider != self._storage.provider_name:
            raise ValueError("Provider penyimpanan versi dokumen tidak aktif pada layanan ini")
        if record.bucket_name != self._storage.bucket_name:
            raise ValueError("Bucket versi dokumen tidak aktif pada layanan ini")
        if record.scan_status in {"PENDING", "REJECTED", "ERROR"}:
            raise ValueError("Dokumen belum lulus pemeriksaan malware")
        if self._scan_mode == "external" and record.scan_status != "CLEAN":
            raise ValueError("Dokumen belum lulus pemeriksaan malware")
        stream = self._storage.open(record.object_key)
        try:
            self._repository.record_download(record, principal)
        except Exception:
            stream.close()
            raise
        return DocumentDownload(record=record, stream=stream)

    @property
    def _initial_scan_status(self) -> str:
        return "PENDING" if self._scan_mode == "external" else "NOT_CONFIGURED"

    def _best_effort_delete(self, object_key: str) -> None:
        try:
            self._storage.delete(object_key)
        except Exception:
            logger.exception(
                "document_storage_compensation_failed",
                extra={"object_key": object_key},
            )

    @staticmethod
    def _require_upload_role(principal: Principal) -> None:
        if not principal.roles.intersection(_UPLOAD_ROLES):
            raise AuthorizationDenied("Role tidak diizinkan mengunggah dokumen")

    @staticmethod
    def _resolve_upload_division(requested: str | None, principal: Principal) -> str | None:
        division_code = requested.strip().upper() if requested else None
        if Role.DIRECTOR in principal.roles:
            return division_code
        if Role.IT_ADMIN in principal.roles:
            if division_code not in {None, "IT"}:
                raise AuthorizationDenied("IT hanya dapat memiliki dokumen divisi IT")
            return "IT"
        if division_code is None:
            if len(principal.division_codes) != 1:
                raise ValueError("division_code wajib dipilih sesuai penugasan pengguna")
            return next(iter(principal.division_codes))
        if division_code not in principal.division_codes:
            raise AuthorizationDenied("Pengguna tidak ditugaskan pada divisi dokumen")
        return division_code

    @staticmethod
    def _authorize_version_upload(record: DocumentRecord, principal: Principal) -> None:
        if record.project_id is not None and not principal.can_access_project(record.project_id):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke proyek dokumen")
        if Role.DIRECTOR in principal.roles:
            return
        if Role.IT_ADMIN in principal.roles:
            if record.division_code != "IT":
                raise AuthorizationDenied("IT bukan business owner dokumen ini")
            return
        if record.division_code is None or record.division_code not in principal.division_codes:
            raise AuthorizationDenied("Pengguna bukan pemilik bisnis dokumen")

    @staticmethod
    def _authorize_download(record: DocumentRecord, principal: Principal) -> None:
        if record.project_id is not None and not principal.can_access_project(record.project_id):
            raise AuthorizationDenied("Pengguna tidak memiliki akses ke proyek dokumen")
        if Role.DIRECTOR in principal.roles or Role.AUDITOR in principal.roles:
            return
        if Role.IT_ADMIN in principal.roles:
            if record.division_code != "IT" and not (
                record.division_code is None and record.classification == "PUBLIC"
            ):
                raise AuthorizationDenied("IT bukan business owner dokumen ini")
            return
        if Role.AI_EXECUTIVE in principal.roles:
            if record.classification == "RESTRICTED":
                raise AuthorizationDenied("Dokumen restricted tidak tersedia untuk AI Executive")
            return
        if (
            record.division_code is not None
            and record.division_code not in principal.division_codes
        ):
            raise AuthorizationDenied("Dokumen dimiliki divisi lain")
        if (
            record.division_code is None
            and record.classification in {"CONFIDENTIAL", "RESTRICTED"}
        ):
            raise AuthorizationDenied(
                "Dokumen bersama rahasia memerlukan akses tingkat organisasi"
            )

    @staticmethod
    def _object_key(
        organization_id: UUID,
        project_id: UUID | None,
        document_id: UUID,
        version_id: UUID,
        extension: str,
    ) -> str:
        scope = str(project_id) if project_id else "shared"
        return f"{organization_id}/{scope}/{document_id}/{version_id}{extension}"


def inspect_upload(
    stream: BinaryIO,
    *,
    filename: str | None,
    declared_media_type: str | None,
    max_upload_bytes: int,
) -> InspectedUpload:
    safe_name = _safe_filename(filename)
    extension = PurePosixPath(safe_name.lower()).suffix
    media_definition = _MEDIA_TYPES.get(extension)
    if media_definition is None:
        raise ValueError("Jenis berkas tidak didukung")
    canonical_media_type, accepted_declared_types = media_definition
    normalized_declared = (
        (declared_media_type or "application/octet-stream").split(";", 1)[0].strip()
    )
    if normalized_declared not in accepted_declared_types:
        raise ValueError("Media type tidak sesuai dengan ekstensi berkas")

    digest = hashlib.sha256()
    size_bytes = 0
    first_bytes = b""
    text_decoder = (
        codecs.getincrementaldecoder("utf-8")() if extension in {".txt", ".csv"} else None
    )
    stream.seek(0)
    while chunk := stream.read(1024 * 1024):
        size_bytes += len(chunk)
        if size_bytes > max_upload_bytes:
            raise ValueError(f"Ukuran berkas melebihi batas {max_upload_bytes} byte")
        if len(first_bytes) < 8192:
            first_bytes += chunk[: 8192 - len(first_bytes)]
        if text_decoder is not None:
            if b"\x00" in chunk:
                raise ValueError("Berkas teks mengandung data biner")
            try:
                text_decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                raise ValueError("Berkas teks wajib menggunakan UTF-8") from exc
        digest.update(chunk)
    if size_bytes == 0:
        raise ValueError("Berkas kosong tidak dapat diunggah")
    if text_decoder is not None:
        try:
            text_decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise ValueError("Berkas teks wajib menggunakan UTF-8") from exc
    _validate_content(stream, extension, first_bytes)
    stream.seek(0)
    return InspectedUpload(
        original_filename=safe_name,
        extension=extension,
        media_type=canonical_media_type,
        size_bytes=size_bytes,
        sha256=digest.hexdigest(),
    )


def _safe_filename(filename: str | None) -> str:
    if filename is None:
        raise ValueError("Nama berkas wajib tersedia")
    basename = filename.replace("\\", "/").split("/")[-1].strip()
    if not basename or len(basename) > 240 or re.search(r"[\x00-\x1f\x7f]", basename):
        raise ValueError("Nama berkas tidak valid")
    return basename


def _validate_content(stream: BinaryIO, extension: str, first_bytes: bytes) -> None:
    if extension == ".pdf" and not first_bytes.startswith(b"%PDF-"):
        raise ValueError("Isi berkas bukan PDF yang valid")
    if extension == ".png" and not first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Isi berkas bukan PNG yang valid")
    if extension in {".jpg", ".jpeg"} and not first_bytes.startswith(b"\xff\xd8\xff"):
        raise ValueError("Isi berkas bukan JPEG yang valid")
    if extension in {".txt", ".csv"}:
        if b"\x00" in first_bytes:
            raise ValueError("Berkas teks mengandung data biner")
        try:
            first_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Berkas teks wajib menggunakan UTF-8") from exc
    if extension in {".docx", ".xlsx"}:
        stream.seek(0)
        try:
            with zipfile.ZipFile(stream) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                total_uncompressed = sum(entry.file_size for entry in entries)
                if (
                    len(names) > 10_000
                    or total_uncompressed > 250 * 1024 * 1024
                    or total_uncompressed > max(1, sum(entry.compress_size for entry in entries))
                    * 100
                    or "[Content_Types].xml" not in names
                ):
                    raise ValueError("Struktur dokumen Office tidak valid")
                required_prefix = "word/" if extension == ".docx" else "xl/"
                if not any(name.startswith(required_prefix) for name in names):
                    raise ValueError("Jenis dokumen Office tidak sesuai ekstensi")
        except zipfile.BadZipFile as exc:
            raise ValueError("Dokumen Office bukan arsip yang valid") from exc

"""Safe local intake for documents attached to a Genesis conversation.

The intake boundary stores the original file without executing it. It extracts
only bounded text for a human preview; it never makes an uploaded file
evidence, a canonical document, or a model input by itself.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import importlib
import io
import json
import os
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4
from xml.etree import ElementTree

import psycopg
from fastapi import UploadFile
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.config import Settings
from alos.documents.center import DocumentCenterRepository, DocumentDraftRequest, DocumentRecord
from alos.persistence.database import psycopg_url

GenesisUploadExtension = Literal["pdf", "docx", "xlsx", "xls", "csv", "json", "md", "txt"]
GenesisUploadExtractionStatus = Literal[
    "EXTRACTED",
    "NO_TEXT",
    "EXTRACTOR_UNAVAILABLE",
    "TRUNCATED",
]
GenesisUploadStatus = Literal["SOURCE_RECEIVED", "DRAFT_CREATED"]

_SUPPORTED_EXTENSIONS = frozenset(
    {"pdf", "docx", "xlsx", "xls", "csv", "json", "md", "txt"}
)
_MAX_EXTRACTED_CHARACTERS = 200_000
_PREVIEW_CHARACTERS = 5_000
_ZIP_MEMBER_MAX_BYTES = 20 * 1024 * 1024
_ZIP_TOTAL_MAX_BYTES = 50 * 1024 * 1024


class GenesisUploadError(RuntimeError):
    """Safe domain error for an uploaded Genesis source."""


class GenesisUploadNotFoundError(GenesisUploadError):
    """The requested upload is not in the current actor workspace."""


class GenesisUploadStorageError(GenesisUploadError):
    """The configured object store cannot safely handle the request."""


class GenesisUploadRecord(BaseModel):
    """Metadata and a bounded preview, never the original binary."""

    model_config = ConfigDict(extra="forbid")

    genesis_upload_id: UUID
    workspace_id: UUID
    original_filename: str
    extension: GenesisUploadExtension
    declared_content_type: str | None
    byte_size: int
    file_sha256: str
    object_key: str
    status: GenesisUploadStatus
    extraction_status: GenesisUploadExtractionStatus
    extraction_complete: bool
    extracted_characters: int
    extracted_text_sha256: str | None
    preview: str | None
    extraction_note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExtractedText:
    content: str
    status: GenesisUploadExtractionStatus
    complete: bool
    note: str | None = None


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_key: str
    byte_size: int
    file_sha256: str
    local_path: Path


@dataclass(frozen=True, slots=True)
class DraftableGenesisUpload:
    upload_id: UUID
    workspace_id: UUID
    original_filename: str
    extracted_text: str
    file_sha256: str
    extracted_text_sha256: str


class GenesisUploadDocumentDraftRequest(BaseModel):
    """The Director explicitly promotes a complete preview to a canonical DRAFT."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200)
    category: str = Field(default="UPLOADED_SOURCE", pattern=r"^[A-Z][A-Z0-9_ ]{1,79}$")
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] = "INTERNAL"


class FilesystemGenesisUploadStorage:
    """Filesystem object storage with generated paths and atomic writes only."""

    def __init__(self, settings: Settings) -> None:
        self._provider = settings.object_storage_provider
        self._root = settings.object_storage_path
        self._max_bytes = settings.object_storage_max_upload_bytes

    async def store(
        self,
        upload: UploadFile,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        upload_id: UUID,
    ) -> StoredObject:
        if self._provider != "filesystem":
            raise GenesisUploadStorageError(
                "Genesis upload storage is not configured for this environment"
            )
        root = self._root.resolve()
        target_directory = root / "genesis-uploads" / organization_id.hex / workspace_id.hex
        target_directory.mkdir(parents=True, exist_ok=True)
        object_key = f"genesis-uploads/{organization_id.hex}/{workspace_id.hex}/{upload_id.hex}.bin"
        target = root / Path(object_key)
        _require_descendant(root, target)

        digest = hashlib.sha256()
        byte_size = 0
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{upload_id.hex}-",
                suffix=".part",
                dir=target_directory,
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                while chunk := await upload.read(64 * 1024):
                    byte_size += len(chunk)
                    if byte_size > self._max_bytes:
                        raise GenesisUploadError(
                            f"file exceeds the upload limit of {self._max_bytes} bytes"
                        )
                    digest.update(chunk)
                    temporary.write(chunk)
            if byte_size == 0:
                raise GenesisUploadError("uploaded file cannot be empty")
            os.replace(temporary_name, target)
            temporary_name = None
        except OSError as error:
            raise GenesisUploadStorageError("uploaded file could not be stored safely") from error
        finally:
            await upload.close()
            if temporary_name is not None:
                _unlink_if_safe(root, Path(temporary_name))

        return StoredObject(
            object_key=object_key,
            byte_size=byte_size,
            file_sha256=digest.hexdigest(),
            local_path=target,
        )

    def remove(self, object_key: str) -> None:
        if self._provider != "filesystem":
            return
        root = self._root.resolve()
        target = root / Path(object_key)
        _unlink_if_safe(root, target)


class GenesisUploadRepository:
    """Append-only metadata for sources that are awaiting human verification."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def ensure_workspace_actor(
        self, *, organization_id: UUID, actor_user_id: UUID, workspace_id: UUID
    ) -> None:
        with self._connection() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)

    def create(
        self,
        *,
        upload_id: UUID,
        organization_id: UUID,
        workspace_id: UUID,
        actor_user_id: UUID,
        original_filename: str,
        extension: GenesisUploadExtension,
        declared_content_type: str | None,
        stored: StoredObject,
        extracted: ExtractedText,
        correlation_id: UUID,
    ) -> GenesisUploadRecord:
        extracted_sha = _digest_text(extracted.content) if extracted.content else None
        with self._transaction() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            row = connection.execute(
                """
                INSERT INTO genesis.document_uploads (
                    genesis_upload_id, organization_id, workspace_id, uploaded_by_user_id,
                    original_filename, extension, declared_content_type, byte_size,
                    object_key, file_sha256, extraction_status, extraction_complete,
                    extracted_text, extracted_text_sha256, extraction_note
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING genesis_upload_id, workspace_id, original_filename, extension,
                          declared_content_type, byte_size, file_sha256, object_key, status,
                          extraction_status, extraction_complete, extracted_text,
                          extracted_text_sha256, extraction_note, created_at
                """,
                (
                    upload_id,
                    organization_id,
                    workspace_id,
                    actor_user_id,
                    original_filename,
                    extension,
                    declared_content_type,
                    stored.byte_size,
                    stored.object_key,
                    stored.file_sha256,
                    extracted.status,
                    extracted.complete,
                    extracted.content or None,
                    extracted_sha,
                    extracted.note,
                ),
            ).fetchone()
            if row is None:
                raise GenesisUploadError("uploaded file metadata could not be saved")
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                upload_id=upload_id,
                correlation_id=correlation_id,
                metadata={
                    "original_filename": original_filename,
                    "extension": extension,
                    "byte_size": stored.byte_size,
                    "file_sha256": stored.file_sha256,
                    "extraction_status": extracted.status,
                    "extraction_complete": extracted.complete,
                },
            )
        return _record_from_row(row)

    def list_for_workspace(
        self, *, organization_id: UUID, actor_user_id: UUID, workspace_id: UUID
    ) -> list[GenesisUploadRecord]:
        with self._connection() as connection:
            self._require_workspace_actor(connection, organization_id, actor_user_id, workspace_id)
            rows = connection.execute(
                """
                SELECT genesis_upload_id, workspace_id, original_filename, extension,
                       declared_content_type, byte_size, file_sha256, object_key, status,
                       extraction_status, extraction_complete, extracted_text,
                       extracted_text_sha256, extraction_note, created_at
                FROM genesis.document_uploads
                WHERE organization_id = %s AND workspace_id = %s
                ORDER BY created_at DESC, genesis_upload_id DESC
                """,
                (organization_id, workspace_id),
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    def get(
        self,
        upload_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisUploadRecord:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT upload.genesis_upload_id, upload.workspace_id, upload.original_filename,
                       upload.extension, upload.declared_content_type, upload.byte_size,
                       upload.file_sha256, upload.object_key, upload.status,
                       upload.extraction_status, upload.extraction_complete, upload.extracted_text,
                       upload.extracted_text_sha256, upload.extraction_note, upload.created_at
                FROM genesis.document_uploads AS upload
                JOIN workspace.memberships AS membership
                  ON membership.workspace_id = upload.workspace_id
                WHERE upload.genesis_upload_id = %s AND upload.organization_id = %s
                  AND membership.user_id = %s
                """,
                (upload_id, organization_id, actor_user_id),
            ).fetchone()
        if row is None:
            raise GenesisUploadNotFoundError("uploaded Genesis source was not found")
        return _record_from_row(row)

    def get_draftable_upload(
        self,
        upload_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> DraftableGenesisUpload:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT upload.genesis_upload_id, upload.workspace_id, upload.original_filename,
                       upload.extracted_text, upload.file_sha256, upload.extracted_text_sha256,
                       upload.status, upload.extraction_status, upload.extraction_complete
                FROM genesis.document_uploads AS upload
                JOIN workspace.memberships AS membership
                  ON membership.workspace_id = upload.workspace_id
                WHERE upload.genesis_upload_id = %s AND upload.organization_id = %s
                  AND membership.user_id = %s
                """,
                (upload_id, organization_id, actor_user_id),
            ).fetchone()
        if row is None:
            raise GenesisUploadNotFoundError("uploaded Genesis source was not found")
        if row["status"] != "SOURCE_RECEIVED":
            raise GenesisUploadError("uploaded source has already been saved as a document DRAFT")
        if row["extraction_status"] != "EXTRACTED" or not row["extraction_complete"]:
            raise GenesisUploadError(
                "uploaded source needs a complete text extraction before it can become a DRAFT"
            )
        if not row["extracted_text"] or not row["extracted_text_sha256"]:
            raise GenesisUploadError("uploaded source has no text available for a document DRAFT")
        return DraftableGenesisUpload(
            upload_id=row["genesis_upload_id"],
            workspace_id=row["workspace_id"],
            original_filename=row["original_filename"],
            extracted_text=row["extracted_text"],
            file_sha256=row["file_sha256"],
            extracted_text_sha256=row["extracted_text_sha256"],
        )

    def mark_document_draft_created(
        self,
        upload_id: UUID,
        document_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE genesis.document_uploads AS upload
                SET status = 'DRAFT_CREATED', canonical_document_id = %s
                FROM workspace.memberships AS membership
                WHERE upload.genesis_upload_id = %s AND upload.organization_id = %s
                  AND membership.workspace_id = upload.workspace_id
                  AND membership.user_id = %s AND upload.status = 'SOURCE_RECEIVED'
                RETURNING upload.workspace_id
                """,
                (document_id, upload_id, organization_id, actor_user_id),
            ).fetchone()
            if row is None:
                raise GenesisUploadError(
                    "uploaded source could not be marked as a canonical document DRAFT"
                )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                upload_id=upload_id,
                correlation_id=correlation_id,
                action="GENESIS_UPLOAD_DOCUMENT_DRAFT_CREATED",
                reason="Director promoted a complete Genesis upload to a Document Center DRAFT",
                metadata={
                    "document_id": str(document_id),
                    "workspace_id": str(row["workspace_id"]),
                },
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
            raise GenesisUploadError("active workspace membership is required")

    @staticmethod
    def _append_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        upload_id: UUID,
        correlation_id: UUID,
        metadata: dict[str, object],
        action: str = "GENESIS_DOCUMENT_UPLOADED",
        reason: str = (
            "Director uploaded a document source; it remains outside Genesis retrieval "
            "until reviewed"
        ),
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, 'GENESIS_DOCUMENT_UPLOAD', %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
                action,
                upload_id,
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


class GenesisUploadService:
    """Coordinate bounded upload storage, extraction, and append-only metadata."""

    def __init__(
        self,
        repository: GenesisUploadRepository,
        storage: FilesystemGenesisUploadStorage,
        documents: DocumentCenterRepository,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._documents = documents

    async def upload(
        self,
        upload: UploadFile,
        *,
        workspace_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisUploadRecord:
        original_filename, extension = _validate_upload_filename(upload.filename)
        self._repository.ensure_workspace_actor(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
        )
        upload_id = uuid4()
        stored = await self._storage.store(
            upload,
            organization_id=organization_id,
            workspace_id=workspace_id,
            upload_id=upload_id,
        )
        try:
            extracted = await asyncio.to_thread(_extract_text, stored.local_path, extension)
            return self._repository.create(
                upload_id=upload_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                original_filename=original_filename,
                extension=extension,
                declared_content_type=_clean_content_type(upload.content_type),
                stored=stored,
                extracted=extracted,
                correlation_id=correlation_id,
            )
        except Exception:
            self._storage.remove(stored.object_key)
            raise

    def create_document_draft(
        self,
        upload_id: UUID,
        request: GenesisUploadDocumentDraftRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> DocumentRecord:
        source = self._repository.get_draftable_upload(
            upload_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        title = (
            request.title.strip()
            if request.title is not None
            else _draft_title(source.original_filename)
        )
        content = _document_draft_content(source)
        if len(content) > 50_000:
            raise GenesisUploadError(
                "uploaded text is too large for one canonical DRAFT and needs a segmented review"
            )
        document = self._documents.create_uploaded_source_draft(
            DocumentDraftRequest(
                workspace_id=source.workspace_id,
                title=title,
                content=content,
                category=request.category,
                classification=request.classification,
            ),
            genesis_upload_id=source.upload_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        self._repository.mark_document_draft_created(
            source.upload_id,
            document.document_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        return document


def _validate_upload_filename(filename: str | None) -> tuple[str, GenesisUploadExtension]:
    if filename is None or not filename.strip():
        raise GenesisUploadError("an uploaded file must have a filename")
    normalized = Path(filename).name.strip()
    if normalized != filename.strip() or len(normalized) > 200:
        raise GenesisUploadError("uploaded filename is not valid")
    extension = Path(normalized).suffix.lower().lstrip(".")
    if extension not in _SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
        raise GenesisUploadError(f"unsupported document format; supported formats: {supported}")
    return normalized, cast(GenesisUploadExtension, extension)


def _draft_title(filename: str) -> str:
    stem = Path(filename).stem.strip() or "Dokumen unggahan"
    return f"Draft sumber — {stem}"[:200]


def _document_draft_content(source: DraftableGenesisUpload) -> str:
    return "\n".join(
        (
            f"# {_draft_title(source.original_filename)}",
            "",
            "## Integritas sumber unggahan",
            f"- Nama berkas asli: {source.original_filename}",
            f"- SHA-256 berkas: {source.file_sha256}",
            f"- SHA-256 teks ekstrak: {source.extracted_text_sha256}",
            f"- Genesis upload ID: {source.upload_id}",
            "- Status: DRAFT untuk pemeriksaan manusia.",
            "",
            "## Teks hasil ekstraksi",
            source.extracted_text,
        )
    )


def _extract_text(path: Path, extension: GenesisUploadExtension) -> ExtractedText:
    try:
        if extension in {"txt", "md"}:
            content = _decode_text(path.read_bytes())
        elif extension == "json":
            content = _extract_json(path)
        elif extension == "csv":
            content = _extract_csv(path)
        elif extension == "docx":
            content = _extract_docx(path)
        elif extension == "xlsx":
            content = _extract_xlsx(path)
        elif extension == "pdf":
            content = _extract_pdf(path)
        else:
            content = _extract_xls(path)
    except _ExtractorUnavailable as error:
        return ExtractedText("", "EXTRACTOR_UNAVAILABLE", False, str(error))
    except (OSError, UnicodeDecodeError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
        return ExtractedText("", "NO_TEXT", False, "Text could not be extracted from this file")
    except Exception:
        # Parser libraries process untrusted document structures. A parser failure must remain
        # a reviewable intake result instead of becoming a server error or a model input.
        return ExtractedText("", "NO_TEXT", False, "Text could not be extracted from this file")

    normalized = _normalize_content(content)
    if not normalized:
        return ExtractedText("", "NO_TEXT", False, "No readable text was found in this file")
    if len(normalized) > _MAX_EXTRACTED_CHARACTERS:
        return ExtractedText(
            normalized[:_MAX_EXTRACTED_CHARACTERS],
            "TRUNCATED",
            False,
            "Extracted text exceeds the safe preview limit and needs a reviewed full-text import",
        )
    return ExtractedText(normalized, "EXTRACTED", True)


class _ExtractorUnavailable(RuntimeError):
    pass


def _extract_pdf(path: Path) -> str:
    module = _optional_module("pypdf", "PDF")
    reader = module.PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_xls(path: Path) -> str:
    module = _optional_module("xlrd", "legacy Excel (.xls)")
    workbook = module.open_workbook(path, on_demand=True)
    try:
        lines: list[str] = []
        for sheet_name in workbook.sheet_names():
            sheet = workbook.sheet_by_name(sheet_name)
            lines.append(f"# Sheet: {sheet_name}")
            for row_index in range(sheet.nrows):
                values = [str(value).strip() for value in sheet.row_values(row_index)]
                if any(values):
                    lines.append(" | ".join(values))
        return "\n".join(lines)
    finally:
        workbook.release_resources()


def _optional_module(name: str, label: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise _ExtractorUnavailable(
            f"A reviewed {label} text extractor is not available"
        ) from error


def _extract_json(path: Path) -> str:
    value = json.loads(_decode_text(path.read_bytes()))
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _extract_csv(path: Path) -> str:
    text = _decode_text(path.read_bytes())
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return "\n".join(" | ".join(value.strip() for value in row) for row in reader if any(row))


def _extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        _validate_zip(archive)
        try:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        except KeyError as error:
            raise ValueError("document.xml is missing") from error
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = [
        "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        for paragraph in document.iter(f"{namespace}p")
    ]
    return "\n".join(paragraph for paragraph in paragraphs if paragraph)


def _extract_xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        _validate_zip(archive)
        shared_strings = _xlsx_shared_strings(archive)
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = _xlsx_relationships(archive)
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        relationship_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        lines: list[str] = []
        sheets = workbook.find(f"{namespace}sheets")
        if sheets is None:
            return ""
        for sheet in sheets.findall(f"{namespace}sheet"):
            sheet_name = sheet.attrib.get("name", "Sheet")
            relationship_id = sheet.attrib.get(f"{relationship_namespace}id")
            target = relationships.get(relationship_id or "")
            if target is None:
                continue
            sheet_path = _xlsx_target_path(target)
            try:
                worksheet = ElementTree.fromstring(archive.read(sheet_path))
            except KeyError:
                continue
            lines.append(f"# Sheet: {sheet_name}")
            for row in worksheet.findall(f".//{namespace}row"):
                values = [_xlsx_cell_value(cell, namespace, shared_strings) for cell in row]
                if any(values):
                    lines.append(" | ".join(values))
        return "\n".join(lines)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        tree = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{namespace}t")) for item in tree]


def _xlsx_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    namespace = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    tree = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    return {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in tree.findall(f"{namespace}Relationship")
        if relationship.attrib.get("Type", "").endswith("/worksheet")
    }


def _xlsx_target_path(target: str) -> str:
    cleaned = target.replace("\\", "/").lstrip("/")
    if cleaned.startswith("xl/") or ".." in Path(cleaned).parts:
        raise ValueError("worksheet target is not valid")
    return f"xl/{cleaned}"


def _xlsx_cell_value(
    cell: ElementTree.Element[str], namespace: str, shared_strings: list[str]
) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.findtext(f"{namespace}v", default="")
    if cell_type == "s" and value.isdigit():
        index = int(value)
        return shared_strings[index] if index < len(shared_strings) else ""
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{namespace}t"))
    return value


def _validate_zip(archive: zipfile.ZipFile) -> None:
    total = 0
    for member in archive.infolist():
        if member.file_size > _ZIP_MEMBER_MAX_BYTES:
            raise ValueError("compressed document contains an oversized member")
        total += member.file_size
        if total > _ZIP_TOTAL_MAX_BYTES:
            raise ValueError("compressed document expands beyond the safe extraction limit")


def _decode_text(value: bytes) -> str:
    return value.decode("utf-8-sig")


def _normalize_content(value: str) -> str:
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_content_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized[:200] or None


def _record_from_row(row: Any) -> GenesisUploadRecord:
    content = row["extracted_text"] or ""
    return GenesisUploadRecord(
        genesis_upload_id=row["genesis_upload_id"],
        workspace_id=row["workspace_id"],
        original_filename=row["original_filename"],
        extension=row["extension"],
        declared_content_type=row["declared_content_type"],
        byte_size=row["byte_size"],
        file_sha256=row["file_sha256"],
        object_key=row["object_key"],
        status=row["status"],
        extraction_status=row["extraction_status"],
        extraction_complete=row["extraction_complete"],
        extracted_characters=len(content),
        extracted_text_sha256=row["extracted_text_sha256"],
        preview=content[:_PREVIEW_CHARACTERS] or None,
        extraction_note=row["extraction_note"],
        created_at=row["created_at"],
    )


def _require_descendant(root: Path, target: Path) -> None:
    try:
        target.resolve().relative_to(root)
    except ValueError as error:
        raise GenesisUploadStorageError(
            "upload path escapes the configured object store"
        ) from error


def _unlink_if_safe(root: Path, target: Path) -> None:
    try:
        resolved_target = target.resolve()
        resolved_target.relative_to(root)
    except ValueError:
        return
    try:
        resolved_target.unlink(missing_ok=True)
    except OSError:
        return

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from starlette.datastructures import UploadFile

from alos.config import Settings
from alos.genesis.uploads import (
    DraftableGenesisUpload,
    FilesystemGenesisUploadStorage,
    GenesisUploadDocumentDraftRequest,
    GenesisUploadError,
    GenesisUploadService,
    WithdrawableGenesisUpload,
    _extract_text,
    _validate_upload_filename,
    _validate_uploaded_content,
)


def test_plain_text_json_and_csv_are_extracted_without_running_uploaded_content(
    tmp_path: Path,
) -> None:
    text_path = tmp_path / "rencana.txt"
    text_path.write_text("Rencana\nOperasional", encoding="utf-8")
    json_path = tmp_path / "rencana.json"
    json_path.write_text(json.dumps({"target": "2026", "kpi": ["cashflow"]}), encoding="utf-8")
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("KPI,Target\nCashflow,13 minggu\n", encoding="utf-8")

    text = _extract_text(text_path, "txt")
    structured = _extract_text(json_path, "json")
    spreadsheet = _extract_text(csv_path, "csv")

    assert text.status == "EXTRACTED"
    assert text.complete is True
    assert text.content == "Rencana\nOperasional"
    assert structured.status == "EXTRACTED"
    assert '"target": "2026"' in structured.content
    assert spreadsheet.content == "KPI | Target\nCashflow | 13 minggu"


def test_docx_and_xlsx_are_read_as_bounded_text(tmp_path: Path) -> None:
    docx_path = tmp_path / "rencana.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:p><w:r><w:t>Rencana 2026</w:t></w:r></w:p>
              <w:p><w:r><w:t>KPI utama</w:t></w:r></w:p></w:body></w:document>""",
        )

    xlsx_path = tmp_path / "kpi.xlsx"
    with zipfile.ZipFile(xlsx_path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="KPI" r:id="rId1"/></sheets></workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Indikator</t></si><si><t>Target</t></si>
            </sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
              <row r="2"><c r="A2" t="inlineStr"><is><t>Cashflow</t></is></c>
              <c r="B2"><v>13</v></c></row>
              </sheetData></worksheet>""",
        )

    document = _extract_text(docx_path, "docx")
    workbook = _extract_text(xlsx_path, "xlsx")

    assert document.status == "EXTRACTED"
    assert document.content == "Rencana 2026\nKPI utama"
    assert workbook.status == "EXTRACTED"
    assert workbook.content == "# Sheet: KPI\nIndikator | Target\nCashflow | 13"


def test_unsupported_extension_is_rejected_before_the_file_is_stored() -> None:
    with pytest.raises(GenesisUploadError, match="supported formats"):
        _validate_upload_filename("script.exe")

    with pytest.raises(GenesisUploadError, match="filename is not valid"):
        _validate_upload_filename("../rencana.pdf")


def test_uploaded_content_must_match_the_declared_supported_format(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "bukan-pdf.pdf"
    fake_pdf.write_text("bukan berkas PDF", encoding="utf-8")
    broken_json = tmp_path / "rusak.json"
    broken_json.write_text("{tidak-valid}", encoding="utf-8")
    binary_text = tmp_path / "biner.txt"
    binary_text.write_bytes(b"rencana\x00internal")

    with pytest.raises(GenesisUploadError, match="PDF content"):
        _validate_uploaded_content(fake_pdf, "pdf")
    with pytest.raises(GenesisUploadError, match="JSON content"):
        _validate_uploaded_content(broken_json, "json")
    with pytest.raises(GenesisUploadError, match="binary data"):
        _validate_uploaded_content(binary_text, "txt")


def test_original_upload_is_stored_under_a_generated_path_with_a_digest(tmp_path: Path) -> None:
    storage = FilesystemGenesisUploadStorage(
        Settings(object_storage_path=tmp_path, object_storage_max_upload_bytes=1024)
    )
    content = b"Rencana operasional internal"
    uploaded_file = UploadFile(filename="rencana.txt", file=io.BytesIO(content))

    stored = asyncio.run(
        storage.store(
            uploaded_file,
            organization_id=uuid4(),
            workspace_id=uuid4(),
            upload_id=uuid4(),
        )
    )

    assert stored.byte_size == len(content)
    assert len(stored.file_sha256) == 64
    assert stored.local_path.read_bytes() == content
    assert stored.object_key.endswith(".bin")


def test_complete_upload_is_promoted_to_one_document_center_draft() -> None:
    source = DraftableGenesisUpload(
        upload_id=uuid4(),
        workspace_id=uuid4(),
        original_filename="Rencana Operasional 2026.txt",
        extracted_text="Target: menyiapkan baseline operasional.",
        file_sha256="f" * 64,
        extracted_text_sha256="e" * 64,
    )
    repository = _DraftRepositoryStub(source)
    documents = _DocumentCenterStub()
    service = GenesisUploadService(repository, _StorageStub(), documents)  # type: ignore[arg-type]

    result = service.create_document_draft(
        source.upload_id,
        GenesisUploadDocumentDraftRequest(category="OPERATIONAL"),
        organization_id=uuid4(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert result is documents.result
    assert documents.request.workspace_id == source.workspace_id
    assert documents.request.title == "Draft sumber — Rencana Operasional 2026"
    assert documents.request.category == "OPERATIONAL"
    assert source.file_sha256 in documents.request.content
    assert source.extracted_text_sha256 in documents.request.content
    assert source.extracted_text in documents.request.content
    assert repository.marked == (source.upload_id, documents.result.document_id)


def test_unpromoted_upload_removes_its_file_before_its_preview_is_withdrawn() -> None:
    upload_id = uuid4()
    repository = _WithdrawalRepositoryStub(upload_id)
    storage = _WithdrawalStorageStub()
    service = GenesisUploadService(repository, storage, _DocumentCenterStub())  # type: ignore[arg-type]

    service.withdraw_upload(
        upload_id,
        organization_id=uuid4(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert storage.removed == "genesis-uploads/test/source.bin"
    assert repository.completed == upload_id
    assert repository.cancelled is None


class _DraftRepositoryStub:
    def __init__(self, source: DraftableGenesisUpload) -> None:
        self.source = source
        self.marked: tuple[object, object] | None = None

    def get_draftable_upload(self, *args: object, **kwargs: object) -> DraftableGenesisUpload:
        return self.source

    def mark_document_draft_created(
        self,
        upload_id: object,
        document_id: object,
        **kwargs: object,
    ) -> None:
        self.marked = (upload_id, document_id)


class _StorageStub:
    pass


class _WithdrawalRepositoryStub:
    def __init__(self, upload_id: object) -> None:
        self.upload_id = upload_id
        self.completed: object | None = None
        self.cancelled: object | None = None

    def begin_withdrawal(
        self, upload_id: object, **kwargs: object
    ) -> WithdrawableGenesisUpload:
        assert upload_id == self.upload_id
        return WithdrawableGenesisUpload(
            upload_id=upload_id,  # type: ignore[arg-type]
            object_key="genesis-uploads/test/source.bin",
        )

    def complete_withdrawal(self, upload_id: object, **kwargs: object) -> None:
        self.completed = upload_id

    def cancel_withdrawal(self, upload_id: object, **kwargs: object) -> None:
        self.cancelled = upload_id


class _WithdrawalStorageStub:
    def __init__(self) -> None:
        self.removed: str | None = None

    def remove(self, object_key: str) -> None:
        self.removed = object_key


class _DocumentResultStub:
    def __init__(self) -> None:
        self.document_id = uuid4()


class _DocumentCenterStub:
    def __init__(self) -> None:
        self.request = None
        self.result = _DocumentResultStub()

    def create_uploaded_source_draft(
        self, request: object, **kwargs: object
    ) -> _DocumentResultStub:
        self.request = request
        return self.result

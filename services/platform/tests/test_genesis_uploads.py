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
    FilesystemGenesisUploadStorage,
    GenesisUploadError,
    _extract_text,
    _validate_upload_filename,
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

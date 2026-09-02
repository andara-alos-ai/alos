import hashlib
import json
from datetime import date
from enum import StrEnum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class SourcePackStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    RELEASED = "RELEASED"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class SourceAuthority(StrEnum):
    LOCKED_ORGANIZATION = "LOCKED_ORGANIZATION"
    DESIGN_BASELINE = "DESIGN_BASELINE"
    APPROVED_BUSINESS_SOURCE = "APPROVED_BUSINESS_SOURCE"
    PRIMARY_EVIDENCE = "PRIMARY_EVIDENCE"
    SYNTHETIC_TEST_BASELINE = "SYNTHETIC_TEST_BASELINE"


class SourceType(StrEnum):
    DOCUMENT = "DOCUMENT"
    SYSTEM_BASELINE = "SYSTEM_BASELINE"


class SourceUse(StrEnum):
    ANALYZE = "ANALYZE"
    GENERATE = "GENERATE"
    VALIDATE = "VALIDATE"
    TEST = "TEST"
    DIFF = "DIFF"
    STAGE = "STAGE"
    RELEASE = "RELEASE"
    PRODUCTION_ACTIVATION = "PRODUCTION_ACTIVATION"


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^ALOS-SRC-[A-Z0-9-]{3,80}$")
    source_code: str = Field(
        pattern=r"^[A-Z][A-Z0-9_.:/-]{0,79}$",
        validation_alias=AliasChoices("source_code", "document_key"),
        serialization_alias="source_code",
    )
    title: str = Field(min_length=5, max_length=200)
    source_type: SourceType
    version: str = Field(pattern=r"^\d+\.\d+(?:\.\d+)?$")
    status: SourcePackStatus
    authority: SourceAuthority
    file_name: str | None = Field(default=None, min_length=5, max_length=255)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    size_bytes: int | None = Field(default=None, gt=0)
    domains: tuple[str, ...] = Field(min_length=1)
    notes: tuple[str, ...] = ()

    @field_validator("domains", "notes")
    @classmethod
    def reject_blank_or_duplicate_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in values):
            raise ValueError("Metadata sumber tidak boleh kosong atau memiliki spasi di tepi")
        if len(values) != len(set(values)):
            raise ValueError("Metadata sumber tidak boleh duplikat")
        return values

    @model_validator(mode="after")
    def validate_document_integrity(self) -> "SourceRecord":
        integrity_values = (self.file_name, self.sha256, self.size_bytes)
        if self.source_type == SourceType.DOCUMENT and any(
            value is None for value in integrity_values
        ):
            raise ValueError("Sumber DOCUMENT wajib memiliki nama file, SHA-256, dan ukuran")
        if self.source_type == SourceType.SYSTEM_BASELINE and any(
            value is not None for value in integrity_values
        ):
            raise ValueError("SYSTEM_BASELINE tidak boleh menyamar sebagai berkas eksternal")
        return self


class SourcePack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    pack_id: str = Field(pattern=r"^ALOS-SP-[A-Z0-9-]{3,80}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=5, max_length=200)
    status: SourcePackStatus
    authority: SourceAuthority
    declared_document_date: date
    classification: str = Field(min_length=3, max_length=80)
    decision_basis: str = Field(min_length=20, max_length=1000)
    contains_unratified_values: bool
    allowed_uses: tuple[SourceUse, ...] = Field(min_length=1)
    blocked_uses: tuple[SourceUse, ...] = Field(min_length=1)
    sources: tuple[SourceRecord, ...] = Field(min_length=1)

    @field_validator("allowed_uses", "blocked_uses")
    @classmethod
    def reject_duplicate_uses(cls, values: tuple[SourceUse, ...]) -> tuple[SourceUse, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Daftar penggunaan source pack tidak boleh duplikat")
        return values

    @model_validator(mode="after")
    def validate_pack(self) -> "SourcePack":
        if set(self.allowed_uses) & set(self.blocked_uses):
            raise ValueError("allowed_uses dan blocked_uses tidak boleh tumpang tindih")
        source_ids = [source.source_id for source in self.sources]
        source_codes = [source.source_code for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_id dalam source pack wajib unik")
        if len(source_codes) != len(set(source_codes)):
            raise ValueError("source_code dalam source pack wajib unik")
        if SourceUse.PRODUCTION_ACTIVATION not in self.blocked_uses:
            raise ValueError("Source pack Genesis wajib memblokir aktivasi production langsung")
        if self.status == SourcePackStatus.DRAFT and not self.contains_unratified_values:
            raise ValueError("Source pack DRAFT wajib menandai nilai yang belum diratifikasi")
        if any(source.status != self.status for source in self.sources):
            raise ValueError("Status seluruh source record wajib sama dengan status source pack")
        return self

    @property
    def reference(self) -> str:
        return f"{self.pack_id}@{self.version}"

    @property
    def pack_digest(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

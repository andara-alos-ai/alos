from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigurationStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


class MappingDisposition(StrEnum):
    REUSE = "REUSE"
    EXTEND = "EXTEND"
    CREATE = "CREATE"
    HOLD = "HOLD"


class ActivationMode(StrEnum):
    DESIGN_ONLY = "DESIGN_ONLY"
    BLOCKED = "BLOCKED"
    RELEASE_CONTROLLED = "RELEASE_CONTROLLED"


class ConfigurationMapping(BaseModel):
    """Governed mapping from a reviewed source to one canonical ALOS registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mapping_id: str = Field(pattern=r"^ALOS-CFG-[A-Z0-9-]{3,80}$")
    document_key: str = Field(pattern=r"^(MASTER|[A-N]|DECISION)$")
    name: str = Field(min_length=5, max_length=200)
    target_registry: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    business_owner: str = Field(pattern=r"^[A-Z][A-Z0-9_& -]{1,79}$")
    source_references: tuple[str, ...] = Field(min_length=1)
    status: ConfigurationStatus
    disposition: MappingDisposition
    activation_mode: ActivationMode
    implementation_scope: tuple[str, ...] = Field(min_length=1)
    blocked_by_decisions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @field_validator(
        "source_references",
        "implementation_scope",
        "blocked_by_decisions",
        "notes",
    )
    @classmethod
    def reject_blank_or_duplicate_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in values):
            raise ValueError("Nilai configuration mapping tidak boleh kosong atau berjarak tepi")
        if len(values) != len(set(values)):
            raise ValueError("Nilai configuration mapping tidak boleh duplikat")
        return values

    @field_validator("blocked_by_decisions")
    @classmethod
    def validate_decision_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for decision_id in values:
            prefix, separator, suffix = decision_id.partition("-")
            if prefix != "DEC" or not separator or len(suffix) < 3:
                raise ValueError(f"Decision ID tidak valid: {decision_id}")
        return values

    @model_validator(mode="after")
    def validate_governance_state(self) -> "ConfigurationMapping":
        if self.status == ConfigurationStatus.APPROVED and self.blocked_by_decisions:
            raise ValueError("Configuration APPROVED tidak boleh memiliki keputusan terbuka")
        if self.activation_mode == ActivationMode.BLOCKED and not self.blocked_by_decisions:
            raise ValueError("Configuration BLOCKED wajib menunjuk keputusan penghambat")
        if (
            self.disposition == MappingDisposition.HOLD
            and self.activation_mode != ActivationMode.BLOCKED
        ):
            raise ValueError("Disposition HOLD wajib menggunakan activation mode BLOCKED")
        if (
            self.status != ConfigurationStatus.APPROVED
            and self.activation_mode == ActivationMode.RELEASE_CONTROLLED
        ):
            raise ValueError("Release-controlled hanya berlaku untuk configuration APPROVED")
        return self


class CanonicalConfigurationRegister(BaseModel):
    """Versioned and non-executable mapping register for enterprise configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    register_id: str = Field(pattern=r"^ALOS-CR-[A-Z0-9-]{3,80}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=5, max_length=200)
    status: ConfigurationStatus
    production_effect: bool
    mappings: tuple[ConfigurationMapping, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_register(self) -> "CanonicalConfigurationRegister":
        if self.production_effect:
            raise ValueError(
                "Canonical mapping register tidak boleh berefek langsung ke production"
            )
        mapping_ids = [mapping.mapping_id for mapping in self.mappings]
        target_registries = [mapping.target_registry for mapping in self.mappings]
        if len(mapping_ids) != len(set(mapping_ids)):
            raise ValueError("mapping_id wajib unik dalam register")
        if len(target_registries) != len(set(target_registries)):
            raise ValueError("target_registry wajib unik dalam register")
        required_keys = {"MASTER", *tuple("ABCDEFGHIJKLMN")}
        covered_keys = {mapping.document_key for mapping in self.mappings}
        missing = sorted(required_keys - covered_keys)
        if missing:
            raise ValueError(f"Mapping Master dan Lampiran A-N belum lengkap: {', '.join(missing)}")
        return self

    @property
    def reference(self) -> str:
        return f"{self.register_id}@{self.version}"

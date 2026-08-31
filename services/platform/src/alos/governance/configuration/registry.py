import json
from pathlib import Path

from pydantic import ValidationError

from alos.genesis.source import SourcePackStatus, SourceRegistry, SourceUse
from alos.governance.configuration.models import (
    CanonicalConfigurationRegister,
    ConfigurationStatus,
)


class ConfigurationRegistryError(ValueError):
    """Raised when a canonical configuration mapping violates governance."""


class CanonicalConfigurationRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._definitions_root = definitions_root
        self._sources = SourceRegistry(definitions_root)
        self._cache: tuple[CanonicalConfigurationRegister, ...] | None = None

    def load_all(
        self, *, force_reload: bool = False
    ) -> tuple[CanonicalConfigurationRegister, ...]:
        if self._cache is not None and not force_reload:
            return self._cache
        files = sorted((self._definitions_root / "configuration").glob("*/register.json"))
        if not files:
            raise ConfigurationRegistryError("Tidak ada canonical configuration register")
        registers = tuple(self._load_file(path) for path in files)
        self._validate_registry(registers)
        self._cache = registers
        return registers

    def get(self, register_id: str, version: str | None = None) -> CanonicalConfigurationRegister:
        matches = [
            register
            for register in self.load_all()
            if register.register_id == register_id.upper()
        ]
        if version is not None:
            for register in matches:
                if register.version == version:
                    return register
            raise KeyError(f"{register_id.upper()}@{version}")
        if not matches:
            raise KeyError(register_id.upper())
        return max(matches, key=lambda item: self._semantic_version(item.version))

    def refresh(self) -> tuple[CanonicalConfigurationRegister, ...]:
        self._sources.refresh()
        return self.load_all(force_reload=True)

    @staticmethod
    def _load_file(path: Path) -> CanonicalConfigurationRegister:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return CanonicalConfigurationRegister.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise ConfigurationRegistryError(
                f"Canonical configuration register tidak valid: {path}: {exc}"
            ) from exc

    def _validate_registry(
        self, registers: tuple[CanonicalConfigurationRegister, ...]
    ) -> None:
        register_keys: set[tuple[str, str]] = set()
        mapping_ids: set[str] = set()
        for register in registers:
            key = (register.register_id, register.version)
            if key in register_keys:
                raise ConfigurationRegistryError(
                    f"Kombinasi register dan versi harus unik: {register.reference}"
                )
            register_keys.add(key)
            for mapping in register.mappings:
                if mapping.mapping_id in mapping_ids:
                    raise ConfigurationRegistryError(
                        f"mapping_id harus unik lintas register: {mapping.mapping_id}"
                    )
                mapping_ids.add(mapping.mapping_id)
                self._sources.validate_references(mapping.source_references, SourceUse.ANALYZE)
                if mapping.status == ConfigurationStatus.APPROVED:
                    for reference in mapping.source_references:
                        source_pack = self._sources.resolve_reference(reference)
                        if source_pack.status not in {
                            SourcePackStatus.APPROVED,
                            SourcePackStatus.RELEASED,
                        }:
                            raise ConfigurationRegistryError(
                                f"Configuration APPROVED memakai sumber belum disahkan: {reference}"
                            )

    @staticmethod
    def _semantic_version(version: str) -> tuple[int, int, int]:
        major, minor, patch = version.split(".")
        return int(major), int(minor), int(patch)

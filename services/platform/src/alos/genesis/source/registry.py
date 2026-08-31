import json
from pathlib import Path

from pydantic import ValidationError

from alos.genesis.source.models import SourcePack, SourcePackStatus, SourceUse


class SourceRegistryError(ValueError):
    """Raised when a source pack or source reference violates governance."""


class SourceRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._definitions_root = definitions_root
        self._cache: tuple[SourcePack, ...] | None = None

    def load_all(self, *, force_reload: bool = False) -> tuple[SourcePack, ...]:
        if self._cache is not None and not force_reload:
            return self._cache
        files = sorted((self._definitions_root / "source-packs").glob("*/source-pack.json"))
        if not files:
            raise SourceRegistryError("Tidak ada source pack terdaftar")
        packs = tuple(self._load_file(path) for path in files)
        self._validate_registry(packs)
        self._cache = packs
        return packs

    def get_pack(self, pack_id: str, version: str | None = None) -> SourcePack:
        matches = [pack for pack in self.load_all() if pack.pack_id == pack_id.upper()]
        if version is not None:
            for pack in matches:
                if pack.version == version:
                    return pack
            raise KeyError(f"{pack_id.upper()}@{version}")
        if not matches:
            raise KeyError(pack_id.upper())
        return max(matches, key=lambda item: self._semantic_version(item.version))

    def validate_references(self, references: tuple[str, ...], required_use: SourceUse) -> None:
        if not references:
            raise SourceRegistryError("Genesis wajib memiliki source reference")
        for reference in references:
            pack = self.resolve_reference(reference)
            self._validate_use(pack, required_use, reference)

    def resolve_reference(self, reference: str) -> SourcePack:
        """Resolve a versioned pack or individual source ID to its governing pack."""
        return self._resolve_reference(reference)

    def refresh(self) -> tuple[SourcePack, ...]:
        return self.load_all(force_reload=True)

    def _resolve_reference(self, reference: str) -> SourcePack:
        if "@" in reference:
            pack_id, version = reference.rsplit("@", 1)
            try:
                return self.get_pack(pack_id, version)
            except KeyError as exc:
                raise SourceRegistryError(f"Source pack tidak terdaftar: {reference}") from exc
        for pack in self.load_all():
            if any(source.source_id == reference for source in pack.sources):
                return pack
        raise SourceRegistryError(f"Source reference tidak terdaftar: {reference}")

    @staticmethod
    def _validate_use(pack: SourcePack, required_use: SourceUse, reference: str) -> None:
        if required_use in pack.blocked_uses or required_use not in pack.allowed_uses:
            raise SourceRegistryError(
                f"Source {reference} berstatus {pack.status} tidak mengizinkan {required_use}"
            )
        if required_use == SourceUse.STAGE and pack.status not in {
            SourcePackStatus.APPROVED,
            SourcePackStatus.RELEASED,
        }:
            raise SourceRegistryError("Staging memerlukan source pack APPROVED atau RELEASED")
        if required_use == SourceUse.RELEASE and pack.status != SourcePackStatus.RELEASED:
            raise SourceRegistryError("Release memerlukan source pack RELEASED")

    @staticmethod
    def _load_file(path: Path) -> SourcePack:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return SourcePack.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise SourceRegistryError(f"Source pack tidak valid: {path}: {exc}") from exc

    @staticmethod
    def _validate_registry(packs: tuple[SourcePack, ...]) -> None:
        pack_keys: set[tuple[str, str]] = set()
        source_ids: set[str] = set()
        for pack in packs:
            key = (pack.pack_id, pack.version)
            if key in pack_keys:
                raise SourceRegistryError(
                    f"Kombinasi source pack dan versi harus unik: {pack.reference}"
                )
            pack_keys.add(key)
            for source in pack.sources:
                if source.source_id in source_ids:
                    raise SourceRegistryError(
                        f"source_id harus unik lintas source pack: {source.source_id}"
                    )
                source_ids.add(source.source_id)

    @staticmethod
    def _semantic_version(version: str) -> tuple[int, int, int]:
        major, minor, patch = version.split(".")
        return int(major), int(minor), int(patch)

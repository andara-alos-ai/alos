import json
from pathlib import Path

from alos.agents.capabilities.models import CapabilityContract, CapabilityStatus


class CapabilityRegistryError(ValueError):
    """Raised when the capability single source of truth is invalid."""


class CapabilityRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._path = definitions_root / "capabilities" / "registry.json"
        self._cache: tuple[CapabilityContract, ...] | None = None

    def load_all(self, *, force_reload: bool = False) -> tuple[CapabilityContract, ...]:
        if self._cache is not None and not force_reload:
            return self._cache
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "1.0.0":
                raise CapabilityRegistryError("schema_version Capability Registry tidak didukung")
            items = tuple(
                CapabilityContract.model_validate(item) for item in payload["capabilities"]
            )
        except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, CapabilityRegistryError):
                raise
            raise CapabilityRegistryError(f"Capability Registry tidak valid: {exc}") from exc
        keys = [(item.capability_id, item.version) for item in items]
        if len(keys) != len(set(keys)):
            raise CapabilityRegistryError("capability_id dan version wajib unik")
        self._cache = tuple(sorted(items, key=lambda item: (item.capability_id, item.version)))
        return self._cache

    def refresh(self) -> tuple[CapabilityContract, ...]:
        return self.load_all(force_reload=True)

    @property
    def exists(self) -> bool:
        return self._path.is_file()

    def get(self, capability_id: str, version: str | None = None) -> CapabilityContract:
        matches = [item for item in self.load_all() if item.capability_id == capability_id]
        if version is not None:
            matches = [item for item in matches if item.version == version]
        if not matches:
            raise KeyError(f"{capability_id}@{version}" if version else capability_id)
        return max(matches, key=lambda item: tuple(int(part) for part in item.version.split(".")))

    def validate_references(self, capability_ids: tuple[str, ...]) -> None:
        missing = sorted(set(capability_ids) - {item.capability_id for item in self.load_all()})
        if missing:
            raise CapabilityRegistryError(f"Capability tidak terdaftar: {missing}")
        blocked = sorted(
            capability_id
            for capability_id in capability_ids
            if self.get(capability_id).status
            not in {CapabilityStatus.STAGED, CapabilityStatus.RELEASED}
        )
        if blocked:
            raise CapabilityRegistryError(f"Capability belum runnable: {blocked}")

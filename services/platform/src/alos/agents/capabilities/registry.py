import json
from pathlib import Path

from alos.agents.capabilities.models import CapabilityContract, CapabilityStatus


class CapabilityRegistryError(ValueError):
    """Raised when the capability single source of truth is invalid."""


class CapabilityRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._path = definitions_root / "capabilities" / "registry.json"
        self._profiles_path = definitions_root / "capabilities" / "schema-profiles.json"
        self._cache: tuple[CapabilityContract, ...] | None = None

    @property
    def definitions_root(self) -> Path:
        return self._path.parents[1]

    def load_all(self, *, force_reload: bool = False) -> tuple[CapabilityContract, ...]:
        if self._cache is not None and not force_reload:
            return self._cache
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "1.0.0":
                raise CapabilityRegistryError("schema_version Capability Registry tidak didukung")
            profiles_payload = json.loads(self._profiles_path.read_text(encoding="utf-8"))
            if profiles_payload.get("schema_version") != "1.0.0":
                raise CapabilityRegistryError("schema_version Capability Schema tidak didukung")
            profiles = profiles_payload["profiles"]
            if not isinstance(profiles, dict):
                raise CapabilityRegistryError("Capability Schema profiles wajib object")
            raw_capabilities = payload["capabilities"]
            handler_ids = {item["handler_id"] for item in raw_capabilities}
            missing_profiles = sorted(handler_ids - set(profiles))
            unused_profiles = sorted(set(profiles) - handler_ids)
            if missing_profiles or unused_profiles:
                raise CapabilityRegistryError(
                    "Capability Schema tidak konsisten dengan handler registry; "
                    f"missing={missing_profiles}, unused={unused_profiles}"
                )
            items = tuple(
                CapabilityContract.model_validate(
                    self._with_profile(item, profiles[item["handler_id"]])
                )
                for item in raw_capabilities
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

    @staticmethod
    def _with_profile(
        item: dict[str, object], profile_value: object
    ) -> dict[str, object]:
        if not isinstance(profile_value, dict):
            raise CapabilityRegistryError("Capability Schema profile wajib object")
        input_properties = profile_value.get("input_properties")
        output_properties = profile_value.get("output_properties")
        input_required = profile_value.get("input_required")
        output_required = profile_value.get("output_required")
        if not isinstance(input_properties, dict) or not isinstance(output_properties, dict):
            raise CapabilityRegistryError("Capability Schema properties wajib object")
        if not isinstance(input_required, list) or not isinstance(output_required, list):
            raise CapabilityRegistryError("Capability Schema required wajib array")
        enriched = dict(item)
        enriched["input_schema"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                **input_properties,
                "data_classification": {
                    "type": "string",
                    "enum": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"],
                },
            },
            "required": input_required,
        }
        enriched["output_schema"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                **output_properties,
                "database_verification_required": {"type": "boolean"},
            },
            "required": output_required,
        }
        return enriched

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

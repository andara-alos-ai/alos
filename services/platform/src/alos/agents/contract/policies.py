"""Versioned model and permission policy references used by logical contracts."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

REFERENCE_PATTERN = r"^[a-z][a-z0-9.-]{2,127}@\d+\.\d+\.\d+$"


class ModelPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(pattern=r"^[a-z][a-z0-9.-]{2,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    primary_provider: str = Field(pattern=r"^openai$")
    fallback_provider: str = Field(pattern=r"^(anthropic|disabled)$")
    local_testing_only: bool
    max_output_tokens: int = Field(ge=32, le=8192)
    status: str = Field(pattern=r"^(STAGED|RELEASED)$")


class PermissionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(pattern=r"^[a-z][a-z0-9.-]{2,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    allowed_tool_effects: tuple[str, ...] = Field(min_length=1)
    human_review_required: bool
    status: str = Field(pattern=r"^(STAGED|RELEASED)$")


class ContractPolicyRegistry:
    """Small, fail-closed registries for policy references in Agent Contract."""

    def __init__(self, definitions_root: Path) -> None:
        self._directory = definitions_root / "policies"
        self._models: tuple[ModelPolicy, ...] | None = None
        self._permissions: tuple[PermissionPolicy, ...] | None = None

    def validate(self, model_ref: str, permission_ref: str) -> None:
        self._resolve(model_ref, self.model_policies(), "Model policy")
        self.permission_policy(permission_ref)

    def permission_policy(self, reference: str) -> PermissionPolicy:
        return self._resolve(reference, self.permission_policies(), "Permission policy")

    def model_policies(self) -> tuple[ModelPolicy, ...]:
        if self._models is None:
            self._models = self._load("model-policies.json", ModelPolicy)
        return self._models

    def permission_policies(self) -> tuple[PermissionPolicy, ...]:
        if self._permissions is None:
            self._permissions = self._load("permission-policies.json", PermissionPolicy)
        return self._permissions

    def _load[T: BaseModel](self, filename: str, model: type[T]) -> tuple[T, ...]:
        path = self._directory / filename
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "1.0.0":
                raise ValueError("schema_version policy tidak didukung")
            items = tuple(model.model_validate(item) for item in payload["policies"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ValueError(f"Policy registry tidak valid: {path}: {exc}") from exc
        keys = {
            (str(item.model_dump()["policy_id"]), str(item.model_dump()["version"]))
            for item in items
        }
        if not items or len(keys) != len(items):
            raise ValueError(f"Policy registry tidak memiliki reference unik: {path}")
        return items

    @staticmethod
    def _resolve[T: ModelPolicy | PermissionPolicy](
        reference: str, items: tuple[T, ...], label: str
    ) -> T:
        policy_id, separator, version = reference.rpartition("@")
        if not separator or not policy_id or not version:
            raise ValueError(f"{label} reference tidak versioned: {reference}")
        for item in items:
            if item.policy_id == policy_id and item.version == version:
                return item
        raise ValueError(f"{label} tidak terdaftar: {reference}")

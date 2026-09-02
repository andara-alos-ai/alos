import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: str = Field(pattern=r"^[a-z][a-z0-9.-]{2,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    purpose: str = Field(min_length=10, max_length=500)
    instructions: str = Field(min_length=20, max_length=8000)
    output_schema: dict[str, object]
    status: str = Field(pattern=r"^(STAGED|RELEASED|RETIRED)$")

    @field_validator("output_schema")
    @classmethod
    def validate_schema(cls, value: dict[str, object]) -> dict[str, object]:
        if value.get("type") != "object" or value.get("additionalProperties") is not False:
            raise ValueError("Prompt output_schema wajib object dan additionalProperties=false")
        return value

    @property
    def prompt_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"status"})
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PromptRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._directory = definitions_root / "prompts"
        self._cache: tuple[PromptDefinition, ...] | None = None

    def load_all(self) -> tuple[PromptDefinition, ...]:
        if self._cache is None:
            files = sorted(self._directory.glob("*.json"))
            if not files:
                raise ValueError("Prompt Registry tidak ditemukan")
            items: list[PromptDefinition] = []
            for path in files:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("schema_version") != "1.0.0":
                    raise ValueError("schema_version Prompt Registry tidak didukung")
                items.extend(PromptDefinition.model_validate(item) for item in payload["prompts"])
            prompts = tuple(items)
            keys = [(item.prompt_id, item.version) for item in prompts]
            if len(keys) != len(set(keys)):
                raise ValueError("prompt_id dan version wajib unik")
            self._cache = prompts
        return self._cache

    def get(self, prompt_id: str, version: str | None = None) -> PromptDefinition:
        matches = [item for item in self.load_all() if item.prompt_id == prompt_id]
        if version is not None:
            matches = [item for item in matches if item.version == version]
        matches = [item for item in matches if item.status in {"STAGED", "RELEASED"}]
        if not matches:
            raise KeyError(f"{prompt_id}@{version}" if version else prompt_id)
        return max(matches, key=lambda item: tuple(int(part) for part in item.version.split(".")))

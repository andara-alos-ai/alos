import json
from pathlib import Path

from alos.tools.models import ToolContract, ToolStatus


class ToolRegistryError(ValueError):
    """Raised when the versioned tool registry is invalid."""


class ToolRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self.definitions_root = definitions_root
        self._definitions_root = definitions_root
        self._cache: tuple[ToolContract, ...] | None = None

    def load_all(self, *, force_reload: bool = False) -> tuple[ToolContract, ...]:
        if self._cache is not None and not force_reload:
            return self._cache
        path = self._definitions_root / "tools" / "registry.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            tools = tuple(ToolContract.model_validate(item) for item in payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ToolRegistryError(f"Tool Registry tidak valid: {path}: {exc}") from exc
        if not tools:
            raise ToolRegistryError("Tool Registry tidak boleh kosong")
        keys = {(tool.tool_id, tool.version) for tool in tools}
        if len(keys) != len(tools):
            raise ToolRegistryError("Kombinasi tool_id dan version harus unik")
        self._cache = tuple(
            sorted(tools, key=lambda item: (item.tool_id, self._semantic_version(item.version)))
        )
        return self._cache

    def refresh(self) -> tuple[ToolContract, ...]:
        return self.load_all(force_reload=True)

    def get(self, tool_id: str, version: str | None = None) -> ToolContract:
        matches = [tool for tool in self.load_all() if tool.tool_id == tool_id]
        if version is not None:
            for tool in matches:
                if tool.version == version:
                    return tool
            raise KeyError(f"{tool_id}@{version}")
        if not matches:
            raise KeyError(tool_id)
        return max(matches, key=lambda item: self._semantic_version(item.version))

    def validate_allowed_tools(self, tool_ids: tuple[str, ...]) -> None:
        missing = sorted(tool_id for tool_id in tool_ids if not self._exists(tool_id))
        if missing:
            raise ToolRegistryError(f"Tool belum terdaftar: {missing}")

    def _exists(self, tool_id: str) -> bool:
        try:
            self.get(tool_id)
        except KeyError:
            return False
        return True

    @staticmethod
    def is_runnable(tool: ToolContract) -> bool:
        return tool.status in {ToolStatus.STAGED, ToolStatus.RELEASED}

    @staticmethod
    def _semantic_version(version: str) -> tuple[int, int, int]:
        major, minor, patch = version.split(".")
        return int(major), int(minor), int(patch)

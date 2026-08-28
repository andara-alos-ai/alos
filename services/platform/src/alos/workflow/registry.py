from pathlib import Path

from alos.workflow.models import WorkflowDefinition


class WorkflowRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._definitions_root = definitions_root

    def load_all(self) -> tuple[WorkflowDefinition, ...]:
        files = sorted((self._definitions_root / "workflows").glob("*/workflow.json"))
        workflows = tuple(
            WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
            for path in files
        )
        if len(workflows) != 6:
            raise ValueError(f"Registry wajib berisi tepat 6 workflow; ditemukan {len(workflows)}")
        if len({item.workflow_id for item in workflows}) != len(workflows):
            raise ValueError("workflow_id harus unik")
        return workflows

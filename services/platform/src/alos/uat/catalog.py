from functools import lru_cache
from pathlib import Path

from alos.uat.models import UatCatalog, UatScenarioDefinition


@lru_cache(maxsize=4)
def load_uat_catalog(definitions_root: Path) -> UatCatalog:
    path = definitions_root / "uat" / "controlled-pilot.json"
    if not path.is_file():
        raise ValueError(f"Katalog UAT tidak ditemukan: {path}")
    return UatCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def scenario_by_id(catalog: UatCatalog, scenario_id: str) -> UatScenarioDefinition:
    for scenario in catalog.scenarios:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError("Skenario UAT tidak ditemukan")

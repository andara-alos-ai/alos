import argparse
from pathlib import Path

from alos.agents.registry import AgentRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validasi definisi ALOS")
    parser.add_argument("--definitions-root", type=Path, default=Path("definitions"))
    args = parser.parse_args()
    registry = AgentRegistry(args.definitions_root)
    agents = registry.load_all()
    core_agents = registry.load_core()
    print(
        f"Valid: {len(core_agents)} Core Agent; "
        f"{len(agents) - len(core_agents)} definisi agent/versi tambahan"
    )


if __name__ == "__main__":
    main()

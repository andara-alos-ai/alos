import argparse
from pathlib import Path

from alos.agents.registry import AgentRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validasi definisi ALOS")
    parser.add_argument("--definitions-root", type=Path, default=Path("definitions"))
    args = parser.parse_args()
    registry = AgentRegistry(args.definitions_root)
    agents = registry.load_all()
    top_level_agents = registry.load_top_level()
    print(
        f"Valid: {len(top_level_agents)} top-level agent; "
        f"{len(agents) - len(top_level_agents)} definisi turunan/versi tambahan"
    )


if __name__ == "__main__":
    main()

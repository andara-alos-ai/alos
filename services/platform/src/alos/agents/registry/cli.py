import argparse
from pathlib import Path

from alos.agents.registry import AgentRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validasi definisi ALOS")
    parser.add_argument("--definitions-root", type=Path, default=Path("definitions"))
    args = parser.parse_args()
    agents = AgentRegistry(args.definitions_root).load_all()
    print(f"Valid: {len(agents)} Core Agent")


if __name__ == "__main__":
    main()

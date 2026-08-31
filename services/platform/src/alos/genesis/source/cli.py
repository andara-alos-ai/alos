import argparse
from pathlib import Path

from alos.genesis.source import SourceRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ALOS source pack registry")
    parser.add_argument("--definitions-root", type=Path, default=Path("definitions"))
    args = parser.parse_args()
    packs = SourceRegistry(args.definitions_root).load_all()
    source_count = sum(len(pack.sources) for pack in packs)
    print(f"Valid: {len(packs)} source pack; {source_count} source record")


if __name__ == "__main__":
    main()

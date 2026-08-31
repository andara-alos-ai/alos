import argparse
from pathlib import Path

from alos.governance.configuration import CanonicalConfigurationRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ALOS canonical configuration registry")
    parser.add_argument("--definitions-root", type=Path, default=Path("definitions"))
    args = parser.parse_args()
    registers = CanonicalConfigurationRegistry(args.definitions_root).load_all()
    mapping_count = sum(len(register.mappings) for register in registers)
    print(f"Valid: {len(registers)} canonical register; {mapping_count} mapping")


if __name__ == "__main__":
    main()

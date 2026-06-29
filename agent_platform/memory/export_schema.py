#!/usr/bin/env python3
"""Export memory JSON Schema bundle for TS / OpenAPI consumers."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_platform.memory.contracts import write_json_schemas

_DEFAULT = Path(__file__).resolve().parent / "schemas" / "memory_bundle.json"


def main() -> None:
    p = argparse.ArgumentParser(description="Export agent_platform memory JSON schemas")
    p.add_argument("-o", "--output", type=Path, default=_DEFAULT)
    args = p.parse_args()
    path = write_json_schemas(args.output)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

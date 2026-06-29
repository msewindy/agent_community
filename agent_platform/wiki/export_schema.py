#!/usr/bin/env python3
"""Export wiki JSON Schema bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_platform.wiki.contracts import write_json_schemas

_DEFAULT = Path(__file__).resolve().parent / "schemas" / "wiki_bundle.json"


def main() -> None:
    p = argparse.ArgumentParser(description="Export agent_platform wiki JSON schemas")
    p.add_argument("-o", "--output", type=Path, default=_DEFAULT)
    args = p.parse_args()
    path = write_json_schemas(args.output)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

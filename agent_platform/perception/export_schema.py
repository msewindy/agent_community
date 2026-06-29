#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from agent_platform.perception.contracts import write_json_schemas

_DEFAULT = Path(__file__).resolve().parent / "schemas" / "perception_bundle.json"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-o", "--output", type=Path, default=_DEFAULT)
    args = p.parse_args()
    print(f"wrote {write_json_schemas(args.output)}")


if __name__ == "__main__":
    main()

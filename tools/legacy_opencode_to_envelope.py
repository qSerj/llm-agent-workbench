#!/usr/bin/env python3
"""Convert an r4.2 OpenCode task bundle to execution envelope v1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.envelope import build_legacy_opencode_envelope, validate_envelope


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_directory", type=Path, help="Path ending in task01")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--human-evaluation", type=Path)
    args = parser.parse_args()

    envelope = build_legacy_opencode_envelope(
        args.task_directory,
        human_evaluation_path=args.human_evaluation,
    )
    validate_envelope(envelope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"validated envelope v{envelope['schema_version']}: {args.output}")


if __name__ == "__main__":
    main()

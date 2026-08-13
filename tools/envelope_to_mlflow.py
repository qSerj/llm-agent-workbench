#!/usr/bin/env python3
"""Validate an execution envelope and project it into local or remote MLflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.mlflow_projection import project_to_mlflow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--experiment", default="llm-agent-workbench")
    parser.add_argument("--correlated-output", type=Path)
    args = parser.parse_args()

    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    run_id, correlated = project_to_mlflow(
        envelope, args.bundle_root.resolve(), args.tracking_uri, args.experiment
    )
    if args.correlated_output:
        args.correlated_output.write_text(
            json.dumps(correlated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"MLflow run: {run_id}")


if __name__ == "__main__":
    main()

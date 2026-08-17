#!/usr/bin/env python3
"""Judge a run that already happened, without solving the task again.

A run keeps the workspace each stage left behind, so the material an evaluation
needs is still there. That means a new evaluator can be applied to results that
cost money weeks ago — and it means changing how we measure never forces us to
pay for the work a second time.

Evaluations are written back into the stored envelope. That is not editing a
record of fact: the fact is the execution, the evaluation is a later judgement
about its output, and the envelope keeps them apart by construction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.envelope import validate_envelope
from workbench.evaluators import EVALUATORS, attach_all
from workbench.experiment import load_experiment


def evaluate_from(experiment: Path | None, only: list[str] | None) -> dict[str, Any]:
    """Which evaluations to run: an experiment's own, narrowed if asked."""
    if experiment is None:
        raise ValueError("нужен --experiment с описанием, где задан блок evaluate")
    loaded = load_experiment(experiment, root=ROOT)
    evaluate = dict(loaded.evaluate)
    if only:
        missing = [name for name in only if name not in evaluate]
        if missing:
            raise ValueError(
                f"в описании нет оценок: {', '.join(missing)}; "
                f"есть: {', '.join(sorted(evaluate)) or 'ни одной'}"
            )
        evaluate = {name: evaluate[name] for name in only}
    return evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envelope", type=Path, help="execution-envelope.json прогона")
    parser.add_argument(
        "--experiment", type=Path, help="описание, из которого берётся блок evaluate"
    )
    parser.add_argument(
        "--only",
        action="append",
        help=f"оценить только это; известны: {', '.join(sorted(EVALUATORS))}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="показать, что будет сделано, и ничего не записывать",
    )
    arguments = parser.parse_args()

    path = arguments.envelope.resolve()
    envelope = json.loads(path.read_text(encoding="utf-8"))
    evaluate = evaluate_from(arguments.experiment, arguments.only)

    print(f"Карточка: {path}")
    print(f"Способ: {envelope['candidate']['id']}")
    print(f"Оценки: {', '.join(sorted(evaluate)) or 'ни одной'}")
    if arguments.dry_run:
        for name, options in sorted(evaluate.items()):
            print(f"  {name}: {json.dumps(options, ensure_ascii=False)}")
        return

    before = {item["id"] for item in envelope["evaluations"]}
    attach_all(envelope, path.parent, evaluate)
    validate_envelope(envelope)
    path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print()
    for item in sorted(envelope["evaluations"], key=lambda x: x["id"]):
        mark = " " if item["id"] in before else "+"
        source = item["evaluator"]["source"]
        print(f" {mark} {item['id']:<14} {source:<10} {item['result']['verdict']:<14}"
              f" {item['rationale']}")
    for item in envelope["observations"]:
        if item["name"] == "judge_cost":
            price = item["value"]
            print(f"\nСудейство: {'неизвестно' if price is None else f'${price:.6f}'}"
                  " — в цену способа не входит.")


if __name__ == "__main__":
    main()

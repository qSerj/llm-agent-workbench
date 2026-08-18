#!/usr/bin/env python3
"""Run every candidate of an experiment and write one execution envelope each."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.chain import DEFAULT_STALL_TIMEOUT, run_candidate, run_directory
from workbench.envelope import validate_envelope
from workbench.evaluators import attach_all
from workbench.experiment import Experiment, load_experiment


def measurement(envelope: dict[str, Any], name: str) -> Any:
    for item in envelope["observations"]:
        if item["name"] == name and "stage_id" not in item:
            return item["value"]
    return None


def summarise(envelopes: list[tuple[str, dict[str, Any]]]) -> None:
    """Print the comparison this project exists to produce."""
    width = 96
    print("\n" + "=" * width)
    print(f"{'способ':<20}{'этапов':>8}{'время, с':>12}{'цена, $':>14}  оценки")
    print("-" * width)
    for candidate_id, envelope in envelopes:
        cost = measurement(envelope, "api_cost")
        wall = measurement(envelope, "wall_time")
        stages = measurement(envelope, "stage_count")
        # Every evaluation, side by side. There is no total across them on
        # purpose: a verdict from a program and one from a model are not the
        # same kind of thing and must not be averaged into a score.
        verdicts = ", ".join(
            f"{item['id']}: {item['result']['verdict']}"
            for item in sorted(envelope["evaluations"], key=lambda x: x["id"])
        )
        print(
            f"{candidate_id:<20}{stages:>8}"
            f"{'—' if wall is None else format(wall, '.1f'):>12}"
            f"{'—' if cost is None else format(cost, '.6f'):>14}"
            f"  {verdicts or '—'}"
        )
    print("=" * width)
    print("Прочерк означает, что величина неизвестна, а не равна нулю.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path, help="experiment YAML")
    parser.add_argument(
        "--output", type=Path, default=Path("executions"), help="where runs are written"
    )
    parser.add_argument(
        "--candidate",
        action="append",
        help="run only this candidate; repeat to select several",
    )
    parser.add_argument("--opencode", default="opencode")
    parser.add_argument("--heartbeat", type=int, default=30)
    parser.add_argument(
        "--stall-timeout",
        type=int,
        default=DEFAULT_STALL_TIMEOUT,
        help="прекратить этап, если opencode молчит столько секунд; 0 — не прекращать",
    )
    arguments = parser.parse_args()

    experiment: Experiment = load_experiment(arguments.experiment, root=ROOT)
    selected = experiment.candidates
    if arguments.candidate:
        selected = [experiment.candidate(name) for name in arguments.candidate]

    print(f"Эксперимент: {experiment.id}")
    print(f"Вопрос: {experiment.question}")
    print(f"Рабочее пространство: {experiment.workspace}")
    print(f"Способов: {len(selected)}, повторений: {experiment.repetitions}")

    today = datetime.now(UTC).date().isoformat()
    run_root = run_directory(arguments.output, experiment.id, today)
    print(f"Каталог прогона: {run_root}")

    produced: list[tuple[str, dict[str, Any]]] = []
    for candidate in selected:
        for repetition in range(1, experiment.repetitions + 1):
            directory = run_root / f"{candidate.id}-r{repetition}"
            envelope = run_candidate(
                experiment_id=experiment.id,
                candidate_id=candidate.id,
                task=experiment.task,
                case=experiment.case,
                specs=candidate.stages,
                source_workspace=experiment.workspace,
                output_directory=directory,
                repetition=repetition,
                opencode=arguments.opencode,
                heartbeat=arguments.heartbeat,
                stall_timeout=arguments.stall_timeout,
            )
            attach_all(envelope, directory, experiment.evaluate)

            validate_envelope(envelope)
            target = directory / "execution-envelope.json"
            target.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"  карточка: {target}")
            produced.append((f"{candidate.id}-r{repetition}", envelope))

    if produced:
        summarise(produced)


if __name__ == "__main__":
    main()

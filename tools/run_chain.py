#!/usr/bin/env python3
"""Run every candidate of an experiment and write one execution envelope each."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.chain import run_candidate
from workbench.citations import citation_evaluation
from workbench.envelope import file_artifact, validate_envelope
from workbench.experiment import Experiment, load_experiment


def final_workspace(envelope: dict[str, Any], bundle_root: Path) -> Path | None:
    """Locate the workspace the last stage left behind, via the envelope itself."""
    stages = envelope.get("stages") or []
    if not stages or not stages[-1]["output_artifact_ids"]:
        return None
    artifact_id = stages[-1]["output_artifact_ids"][0]
    for artifact in envelope["artifacts"]:
        if artifact["id"] == artifact_id and "path" in artifact["location"]:
            return bundle_root / artifact["location"]["path"]
    return None


def attach_citation_check(
    envelope: dict[str, Any], bundle_root: Path, document_relative: str
) -> None:
    """Record the produced document and the deterministic check over it."""
    workspace = final_workspace(envelope, bundle_root)
    if workspace is None:
        return
    document = workspace / document_relative
    if not document.is_file():
        print(f"  документ не создан: {document_relative}")
        return

    artifact_id = "final-document"
    envelope["artifacts"].append(
        file_artifact(artifact_id, "OUTPUT", document, bundle_root, "text/markdown")
    )
    envelope["evaluations"].append(
        citation_evaluation(
            evaluation_id="citations",
            document=document,
            root=workspace,
            subject_artifact_id=artifact_id,
            evidence_artifact_ids=[artifact_id],
        )
    )


def measurement(envelope: dict[str, Any], name: str) -> Any:
    for item in envelope["observations"]:
        if item["name"] == name and "stage_id" not in item:
            return item["value"]
    return None


def summarise(envelopes: list[tuple[str, dict[str, Any]]]) -> None:
    """Print the comparison this project exists to produce."""
    width = 80
    print("\n" + "=" * width)
    print(f"{'способ':<20}{'этапов':>8}{'время, с':>12}{'цена, $':>14}{'ссылки':>16}")
    print("-" * width)
    for candidate_id, envelope in envelopes:
        cost = measurement(envelope, "api_cost")
        wall = measurement(envelope, "wall_time")
        stages = measurement(envelope, "stage_count")
        verdict = "—"
        for item in envelope["evaluations"]:
            if item["id"] == "citations":
                verdict = item["result"]["verdict"]
        print(
            f"{candidate_id:<20}{stages:>8}"
            f"{'—' if wall is None else format(wall, '.1f'):>12}"
            f"{'—' if cost is None else format(cost, '.6f'):>14}"
            f"{verdict:>16}"
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
    arguments = parser.parse_args()

    experiment: Experiment = load_experiment(arguments.experiment, root=ROOT)
    selected = experiment.candidates
    if arguments.candidate:
        selected = [experiment.candidate(name) for name in arguments.candidate]

    print(f"Эксперимент: {experiment.id}")
    print(f"Вопрос: {experiment.question}")
    print(f"Рабочее пространство: {experiment.workspace}")
    print(f"Способов: {len(selected)}, повторений: {experiment.repetitions}")

    produced: list[tuple[str, dict[str, Any]]] = []
    for candidate in selected:
        for repetition in range(1, experiment.repetitions + 1):
            directory = (
                arguments.output / experiment.id / f"{candidate.id}-r{repetition}"
            )
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
            )
            document = experiment.evaluate.get("citations")
            if document:
                attach_citation_check(envelope, directory, document)

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

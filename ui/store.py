"""Read execution envelopes off disk and expose them as comparable runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workbench.storage import is_hidden

ENVELOPE_NAME = "execution-envelope.json"

# Fixed slot per stage role. Colour follows the entity, never its rank, so a
# filtered-out role never repaints the ones that remain.
ROLE_SLOTS = {"SOLVER": 1, "REVIEWER": 2, "FIXER": 3, "OTHER": 4}


@dataclass
class Stage:
    id: str
    role: str
    depends_on: list[str]
    wall_time: float | None
    api_cost: float | None
    tool_calls: int | None
    failed_tool_calls: int | None
    total_tokens: int | None

    @property
    def slot(self) -> int:
        return ROLE_SLOTS.get(self.role, 4)


@dataclass
class Run:
    execution_id: str
    experiment_id: str
    candidate_id: str
    repetition: int
    directory: Path
    envelope: dict[str, Any]
    stages: list[Stage]
    stamp: str = ""

    @property
    def label(self) -> str:
        return f"{self.candidate_id}·r{self.repetition}"

    @property
    def day(self) -> str:
        """When the run happened, taken from the envelope rather than the path.

        The directory stamp only exists for runs written after runs began to be
        grouped by day; the envelope has carried the time all along.
        """
        return self.started_at[:10]

    @property
    def moment(self) -> str:
        return self.started_at[:16].replace("T", " ")

    @property
    def status(self) -> str:
        return self.envelope["lifecycle"]["status"]

    @property
    def started_at(self) -> str:
        return self.envelope["lifecycle"]["started_at"]

    @property
    def wall_time(self) -> float | None:
        return self.total("wall_time")

    @property
    def api_cost(self) -> float | None:
        return self.total("api_cost")

    @property
    def stage_count(self) -> int:
        return len(self.stages)

    @property
    def tool_calls(self) -> int | None:
        values = [stage.tool_calls for stage in self.stages]
        return None if any(item is None for item in values) else sum(values)

    @property
    def failed_tool_calls(self) -> int | None:
        values = [stage.failed_tool_calls for stage in self.stages]
        return None if any(item is None for item in values) else sum(values)

    def total(self, name: str) -> Any:
        """Execution-level measurement: the one carrying no stage_id."""
        for item in self.envelope["observations"]:
            if item["name"] == name and "stage_id" not in item:
                return item["value"]
        return None

    def evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        for item in self.envelope["evaluations"]:
            if item["id"] == evaluation_id:
                return item
        return None

    @property
    def citation_verdict(self) -> str | None:
        evaluation = self.evaluation("citations")
        return evaluation["result"]["verdict"] if evaluation else None

    @property
    def citation_checks(self) -> int | None:
        """How many claims the check could look at.

        Zero is not the same as no evaluation: it means the document made no
        claim tied to ``path:line``, so there was nothing to verify. Reading that
        as a missing measurement would hide a real finding about the candidate.
        """
        evaluation = self.evaluation("citations")
        return len(evaluation["result"].get("checks", [])) if evaluation else None

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        return self.envelope["artifacts"]

    def stage_measurements(self, name: str) -> list[tuple[Stage, Any]]:
        return [(stage, getattr(stage, name)) for stage in self.stages]


def stage_value(observations: list[dict[str, Any]], stage_id: str, name: str) -> Any:
    for item in observations:
        if item.get("stage_id") == stage_id and item["name"] == name:
            return item["value"]
    return None


def placement(envelope_path: Path, root: Path) -> tuple[str, str]:
    """Read the experiment and the run stamp off the path.

    Runs are grouped by day — ``<experiment>/<date>/<candidate>-r<n>`` — but runs
    written before that grouping existed sit one level higher, and the shell has
    to keep showing them.
    """
    parts = envelope_path.parent.relative_to(root).parts
    if len(parts) >= 3:
        return parts[0], parts[1]
    return (parts[0] if parts else ""), ""


def load_run(envelope_path: Path, root: Path | None = None) -> Run:
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    observations = envelope["observations"]
    stages = [
        Stage(
            id=item["id"],
            role=item["role"],
            depends_on=item["depends_on"],
            wall_time=stage_value(observations, item["id"], "wall_time"),
            api_cost=stage_value(observations, item["id"], "api_cost"),
            tool_calls=stage_value(observations, item["id"], "tool_calls"),
            failed_tool_calls=stage_value(
                observations, item["id"], "failed_tool_calls"
            ),
            total_tokens=stage_value(observations, item["id"], "total_tokens"),
        )
        for item in envelope.get("stages", [])
    ]
    directory = envelope_path.parent
    experiment_id, stamp = placement(
        envelope_path, root if root is not None else directory.parent.parent
    )
    return Run(
        execution_id=envelope["execution_id"],
        experiment_id=experiment_id,
        candidate_id=envelope["candidate"]["id"],
        repetition=envelope["repetition"],
        directory=directory,
        envelope=envelope,
        stages=stages,
        stamp=stamp,
    )


class Store:
    """Every run found under the executions directory, newest experiment first."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def runs(self) -> list[Run]:
        if not self.root.is_dir():
            return []
        found: list[Run] = []
        for path in sorted(self.root.rglob(ENVELOPE_NAME)):
            # A run keeps copies of the workspace; an envelope that a candidate
            # happened to produce inside one is data, not a run of ours. Deleted
            # runs live under a dot-directory and are equally not ours to list.
            if {"input-workspace", "stages"} & set(path.parts):
                continue
            if is_hidden(path, self.root):
                continue
            try:
                found.append(load_run(path, self.root))
            except (OSError, ValueError, KeyError) as error:
                print(f"пропущена карточка {path}: {error}")
        found.sort(
            key=lambda run: (
                run.experiment_id,
                run.started_at,
                run.candidate_id,
                run.repetition,
            )
        )
        return found

    def experiments(self) -> dict[str, list[Run]]:
        grouped: dict[str, list[Run]] = {}
        for run in self.runs():
            grouped.setdefault(run.experiment_id, []).append(run)
        return grouped

    def run(self, execution_id: str) -> Run | None:
        for run in self.runs():
            if run.execution_id == execution_id:
                return run
        return None

    def select(self, execution_ids: list[str]) -> list[Run]:
        by_id = {run.execution_id: run for run in self.runs()}
        return [by_id[item] for item in execution_ids if item in by_id]

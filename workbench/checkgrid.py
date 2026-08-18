"""Line up the checks of several runs so the differences are readable.

A verdict is a poor comparison. One red check makes a run ``FAIL``, so two
candidates that failed for entirely different reasons look identical, and two
that passed tell you nothing about whether the measurement can tell them apart
at all. The interesting question — does this reference actually distinguish the
ways of working? — is answered check by check.

The rules here are the project's rules, not new ones:

* a check one run does not have is **unknown**, not failed. The cell is empty
  and reads as a dash (ADR 0004);
* order is order of first appearance, never sorted. A suite's order is written
  by a person and carries meaning;
* nothing is totalled. A share of green is not a score.

It takes envelopes rather than the shell's ``Run`` objects, so it stays
offline-testable and the shell keeps its adapter role.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Cell:
    """One run's answer to one check. ``outcome is None`` means it has none."""

    outcome: str | None = None
    rationale: str = ""
    value: Any = None

    @property
    def known(self) -> bool:
        return self.outcome is not None


@dataclass
class Row:
    """One check across every run being compared."""

    evaluation: str
    check: str
    cells: list[Cell] = field(default_factory=list)

    @property
    def present(self) -> int:
        return sum(1 for cell in self.cells if cell.known)

    @property
    def agreed(self) -> bool:
        """True when every run that answered gave the same answer."""
        answers = {cell.outcome for cell in self.cells if cell.known}
        return len(answers) <= 1

    @property
    def comparable(self) -> bool:
        """Two runs or more actually answered; otherwise there is no comparison."""
        return self.present > 1


def evaluations_of(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(envelope.get("evaluations") or [], key=lambda item: item["id"])


def verdicts(envelope: dict[str, Any]) -> dict[str, str]:
    """Every evaluation of a run by name, not just the one a template knows."""
    return {item["id"]: item["result"]["verdict"] for item in evaluations_of(envelope)}


def evaluation_ids(envelopes: list[dict[str, Any]]) -> list[str]:
    """Every evaluation name present in any of the runs, in a stable order."""
    found: list[str] = []
    for envelope in envelopes:
        for item in evaluations_of(envelope):
            if item["id"] not in found:
                found.append(item["id"])
    return found


def checks_of(envelope: dict[str, Any], evaluation_id: str) -> dict[str, dict[str, Any]]:
    for item in envelope.get("evaluations") or []:
        if item["id"] == evaluation_id:
            return {
                str(check["id"]): check
                for check in (item["result"].get("checks") or [])
            }
    return {}


def check_grid(
    envelopes: list[dict[str, Any]], only: str | None = None
) -> list[Row]:
    """One row per check, one cell per run, in first-appearance order."""
    rows: list[Row] = []
    names = [only] if only else evaluation_ids(envelopes)
    for evaluation_id in names:
        per_run = [checks_of(envelope, evaluation_id) for envelope in envelopes]
        ordered: list[str] = []
        for found in per_run:
            for check_id in found:
                if check_id not in ordered:
                    ordered.append(check_id)
        for check_id in ordered:
            row = Row(evaluation=evaluation_id, check=check_id)
            for found in per_run:
                check = found.get(check_id)
                if check is None:
                    row.cells.append(Cell())
                else:
                    row.cells.append(
                        Cell(
                            outcome=str(check.get("outcome") or "UNDETERMINED"),
                            rationale=str(check.get("rationale") or ""),
                            value=check.get("value"),
                        )
                    )
            rows.append(row)
    return rows


def disagreements(rows: list[Row]) -> list[Row]:
    """Only the checks that told the runs apart — the point of comparing."""
    return [row for row in rows if not row.agreed]

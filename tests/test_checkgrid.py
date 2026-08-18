"""Offline tests for lining up checks across runs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.checkgrid import check_grid, disagreements, evaluation_ids, verdicts


def envelope(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    return {"evaluations": evaluations}


def suite(*checks: tuple[str, str], verdict: str = "FAIL") -> dict[str, Any]:
    return {
        "id": "suite",
        "result": {
            "verdict": verdict,
            "checks": [
                {"id": name, "outcome": outcome, "rationale": f"причина {name}"}
                for name, outcome in checks
            ],
        },
    }


class VerdictTests(unittest.TestCase):
    def test_every_evaluation_is_reported_not_just_one(self) -> None:
        found = verdicts(
            envelope(
                [
                    suite(("a", "PASS"), verdict="PASS"),
                    {"id": "citations", "result": {"verdict": "UNDETERMINED"}},
                ]
            )
        )
        self.assertEqual(found, {"suite": "PASS", "citations": "UNDETERMINED"})

    def test_an_evaluation_without_checks_still_has_a_verdict(self) -> None:
        one = envelope([{"id": "citations", "result": {"verdict": "UNDETERMINED"}}])
        self.assertEqual(verdicts(one), {"citations": "UNDETERMINED"})
        self.assertEqual(check_grid([one]), [])

    def test_a_run_without_evaluations_contributes_nothing(self) -> None:
        self.assertEqual(evaluation_ids([envelope([]), {}]), [])
        self.assertEqual(check_grid([envelope([]), {}]), [])


class GridTests(unittest.TestCase):
    def test_a_check_one_run_lacks_is_unknown_not_failed(self) -> None:
        rows = check_grid(
            [
                envelope([suite(("a", "PASS"), ("b", "FAIL"))]),
                envelope([suite(("a", "PASS"))]),
            ]
        )
        missing = next(row for row in rows if row.check == "b")
        self.assertIsNone(missing.cells[1].outcome)
        self.assertFalse(missing.cells[1].known)
        self.assertEqual(missing.present, 1)
        self.assertFalse(missing.comparable)

    def test_order_is_first_appearance_and_survives_reordering(self) -> None:
        """A suite's order is written by a person; sorting would scramble it."""
        rows = check_grid(
            [
                envelope([suite(("сначала", "PASS"), ("потом", "FAIL"))]),
                envelope([suite(("потом", "PASS"), ("сначала", "PASS"))]),
            ]
        )
        self.assertEqual([row.check for row in rows], ["сначала", "потом"])

    def test_a_check_only_one_run_has_keeps_its_place(self) -> None:
        rows = check_grid(
            [
                envelope([suite(("a", "PASS"))]),
                envelope([suite(("a", "PASS"), ("свой", "FAIL"))]),
            ]
        )
        self.assertEqual([row.check for row in rows], ["a", "свой"])

    def test_agreement_and_disagreement(self) -> None:
        rows = check_grid(
            [
                envelope([suite(("тот же", "PASS"), ("разный", "PASS"))]),
                envelope([suite(("тот же", "PASS"), ("разный", "UNDETERMINED"))]),
            ]
        )
        agreed = next(row for row in rows if row.check == "тот же")
        differing = next(row for row in rows if row.check == "разный")
        self.assertTrue(agreed.agreed)
        self.assertFalse(differing.agreed)
        self.assertEqual([row.check for row in disagreements(rows)], ["разный"])

    def test_a_lone_answer_is_not_a_disagreement(self) -> None:
        rows = check_grid([envelope([suite(("одна", "FAIL"))]), envelope([])])
        self.assertTrue(rows[0].agreed)
        self.assertFalse(rows[0].comparable)

    def test_one_evaluation_can_be_asked_for_alone(self) -> None:
        both = envelope(
            [
                suite(("a", "PASS")),
                {
                    "id": "citations",
                    "result": {
                        "verdict": "PASS",
                        "checks": [{"id": "src/x.cs:1", "outcome": "PASS"}],
                    },
                },
            ]
        )
        rows = check_grid([both], only="citations")
        self.assertEqual([row.check for row in rows], ["src/x.cs:1"])

    def test_a_missing_outcome_word_is_undetermined(self) -> None:
        one = envelope([{"id": "suite", "result": {"verdict": "UNDETERMINED",
                                                   "checks": [{"id": "a"}]}}])
        self.assertEqual(check_grid([one])[0].cells[0].outcome, "UNDETERMINED")


if __name__ == "__main__":
    unittest.main()

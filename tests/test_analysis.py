"""Парная статистика повторяемых исполнений."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.analysis import Record, record_from_envelope, summarise_comparison
from workbench.experiment import ComparisonSpec

COMPARISON = ComparisonSpec("A/B", "a", "b", "A", "B")


def record(
    candidate: str,
    repetition: int,
    *,
    total: int | None = None,
    reasoning: int | None = None,
    status: str = "SUCCEEDED",
    verdicts: dict[str, str] | None = None,
) -> Record:
    return Record(
        candidate_id=candidate,
        repetition=repetition,
        status=status,
        measurements={"total_tokens": total, "reasoning_tokens": reasoning},
        verdicts=verdicts or {},
    )


class PairedAnalysisTests(unittest.TestCase):
    def test_means_medians_and_two_ratios_use_the_same_complete_pairs(self) -> None:
        records = [
            record("b", 2, total=100),
            record("a", 1, total=20),
            record("b", 1, total=10),
            record("a", 2, total=100),
            record("b", 3, total=30),
            record("a", 3),
        ]
        metric = summarise_comparison(records, COMPARISON, 3).metric("total_tokens")
        self.assertEqual(metric.pair_count, 2)
        self.assertEqual(metric.total_pairs, 3)
        self.assertEqual(metric.numerator_mean, 60)
        self.assertEqual(metric.numerator_median, 60)
        self.assertEqual(metric.denominator_mean, 55)
        self.assertEqual(metric.denominator_median, 55)
        self.assertAlmostEqual(metric.ratio_of_means, 60 / 55)
        self.assertEqual(metric.median_pair_ratio, 1.5)

    def test_zero_denominator_keeps_values_but_not_ratios(self) -> None:
        records = [
            record("a", 1, reasoning=0),
            record("b", 1, reasoning=0),
            record("a", 2, reasoning=1),
            record("b", 2, reasoning=0),
        ]
        metric = summarise_comparison(records, COMPARISON, 2).metric(
            "reasoning_tokens"
        )
        self.assertEqual(metric.pair_count, 2)
        self.assertEqual(metric.ratio_pair_count, 0)
        self.assertIsNone(metric.ratio_of_means)
        self.assertIsNone(metric.median_pair_ratio)

    def test_missing_runs_and_unexpected_repetitions_are_visible(self) -> None:
        records = [
            record("a", 1, total=1),
            record("b", 1, total=1),
            record("a", 4, total=1),
        ]
        summary = summarise_comparison(records, COMPARISON, 3)
        self.assertEqual(summary.repetitions, (1, 2, 3, 4))
        self.assertEqual(summary.missing_numerator, (2, 3))
        self.assertEqual(summary.missing_denominator, (2, 3, 4))

    def test_lifecycle_and_each_evaluation_stay_separate(self) -> None:
        records = [
            record("a", 1, verdicts={"suite": "PASS", "claims": "FAIL"}),
            record("b", 1, verdicts={"suite": "PASS"}),
            record("a", 2, status="FAILED"),
            record("b", 2, verdicts={"suite": "UNDETERMINED"}),
        ]
        summary = summarise_comparison(records, COMPARISON, 2)
        self.assertEqual(summary.lifecycle.numerator.count("FAILED"), 1)
        suite = next(item for item in summary.evaluations if item.name == "suite")
        claims = next(item for item in summary.evaluations if item.name == "claims")
        self.assertEqual(suite.denominator.count("PASS"), 1)
        self.assertEqual(suite.denominator.count("UNDETERMINED"), 1)
        self.assertEqual(suite.numerator.missing, 1)
        self.assertEqual(claims.numerator.count("FAIL"), 1)
        self.assertEqual(claims.denominator.missing, 2)

    def test_duplicate_candidate_repetition_is_rejected(self) -> None:
        records = [record("a", 1), record("a", 1), record("b", 1)]
        with self.assertRaisesRegex(ValueError, "duplicate execution"):
            summarise_comparison(records, COMPARISON, 1)

    def test_envelope_adapter_reads_execution_level_facts(self) -> None:
        envelope = {
            "candidate": {"id": "a"},
            "repetition": 2,
            "lifecycle": {"status": "SUCCEEDED"},
            "observations": [
                {"name": "total_tokens", "value": 42},
                {"name": "total_tokens", "value": 10, "stage_id": "s1"},
            ],
            "evaluations": [{"id": "suite", "result": {"verdict": "PASS"}}],
        }
        adapted = record_from_envelope(envelope)
        self.assertEqual(adapted.measurements["total_tokens"], 42)
        self.assertEqual(adapted.verdicts, {"suite": "PASS"})


if __name__ == "__main__":
    unittest.main()

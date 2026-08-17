"""Offline tests for showing what separates two candidates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.textdiff import diff_lines, differing_prompts, stage_field, stage_rows

SOLVER = {
    "role": "SOLVER",
    "model": "a/model",
    "prompt": "task.md",
    "allow_edit": ["docs/report.md"],
}
REVIEWER_V1 = {
    "role": "REVIEWER",
    "model": "b/model",
    "prompt": "reviewer.md",
    "allow_edit": ["docs/findings.json"],
}
REVIEWER_V2 = {**REVIEWER_V1, "prompt": "reviewer-v2.md"}


class DiffLinesTests(unittest.TestCase):
    def test_identical_text_produces_nothing(self) -> None:
        self.assertEqual(diff_lines("one\ntwo", "one\ntwo", "a", "b"), [])

    def test_a_changed_line_is_marked_both_ways(self) -> None:
        rows = diff_lines("one\ntwo", "one\nthree", "a", "b")
        kinds = [row.kind for row in rows]
        self.assertIn("removed", kinds)
        self.assertIn("added", kinds)
        removed = [row.text for row in rows if row.kind == "removed"]
        added = [row.text for row in rows if row.kind == "added"]
        self.assertEqual(removed, ["two"])
        self.assertEqual(added, ["three"])

    def test_markers_are_stripped_from_the_text(self) -> None:
        """The sign is carried by the kind, so it must not also sit in the text."""
        rows = diff_lines("a", "b", "left", "right")
        for row in rows:
            if row.kind in {"added", "removed"}:
                self.assertFalse(row.text.startswith(("+", "-")))

    def test_the_labels_appear_in_the_heading(self) -> None:
        rows = diff_lines("a", "b", "chain-v1", "chain-v2")
        meta = " ".join(row.text for row in rows if row.kind == "meta")
        self.assertIn("chain-v1", meta)
        self.assertIn("chain-v2", meta)


class StageRowsTests(unittest.TestCase):
    def test_matching_fields_are_marked_the_same(self) -> None:
        rows = stage_rows([SOLVER], [SOLVER])
        self.assertTrue(all(row["same"] for row in rows))

    def test_one_differing_field_is_the_only_difference(self) -> None:
        rows = stage_rows([SOLVER, REVIEWER_V1], [SOLVER, REVIEWER_V2])
        differing = [row for row in rows if not row["same"]]
        self.assertEqual(len(differing), 1)
        self.assertEqual(differing[0]["field"], "prompt")
        self.assertEqual(differing[0]["stage"], 2)

    def test_a_longer_chain_differs_by_its_extra_stage(self) -> None:
        rows = stage_rows([SOLVER], [SOLVER, REVIEWER_V1])
        extra = [row for row in rows if row["stage"] == 2]
        self.assertTrue(all(row["before"] == "" for row in extra))
        self.assertTrue(any(row["after"] == "REVIEWER" for row in extra))

    def test_a_list_field_reads_as_text(self) -> None:
        self.assertEqual(stage_field(SOLVER, "allow_edit"), "docs/report.md")

    def test_an_absent_field_is_empty_not_none(self) -> None:
        self.assertEqual(stage_field({}, "model"), "")


class DifferingPromptsTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return {"reviewer.md": "мягко", "reviewer-v2.md": "строго"}.get(name, "")

    def test_shared_prompts_are_skipped(self) -> None:
        self.assertEqual(differing_prompts([SOLVER], [SOLVER], self.read), [])

    def test_only_the_differing_stage_is_diffed(self) -> None:
        pairs = differing_prompts(
            [SOLVER, REVIEWER_V1], [SOLVER, REVIEWER_V2], self.read
        )
        self.assertEqual(len(pairs), 1)
        before, after, rows = pairs[0]
        self.assertEqual((before, after), ("reviewer.md", "reviewer-v2.md"))
        self.assertIn("строго", [row.text for row in rows])

    def test_a_missing_stage_is_reported_rather_than_raising(self) -> None:
        pairs = differing_prompts([SOLVER], [SOLVER, REVIEWER_V1], self.read)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0], "")


if __name__ == "__main__":
    unittest.main()

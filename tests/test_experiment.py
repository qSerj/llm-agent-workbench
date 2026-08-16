"""Offline tests for reading a short experiment description."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.experiment import load_experiment, versioned_reference

try:
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

MINIMAL = """
id: demo
question: Что дешевле?
workspace: fixture
candidates:
  - id: single
    stages:
      - role: SOLVER
        model: test/model
        prompt: prompts/solve.md
        allow_edit: [docs/report.md]
"""


def make_root(document: str) -> tempfile.TemporaryDirectory:
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name)
    (root / "fixture" / "src").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "prompts" / "solve.md").write_text("solve\n", encoding="utf-8")
    (root / "prompts" / "review.md").write_text("review\n", encoding="utf-8")
    (root / "experiment.yaml").write_text(document, encoding="utf-8")
    return holder


@unittest.skipUnless(HAS_YAML, "PyYAML is not installed")
class LoadExperimentTests(unittest.TestCase):
    def load(self, document: str):
        holder = make_root(document)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        return load_experiment(root / "experiment.yaml", root=root)

    def test_minimal_description_loads(self) -> None:
        experiment = self.load(MINIMAL)
        self.assertEqual(experiment.id, "demo")
        self.assertEqual(experiment.repetitions, 1)
        self.assertEqual(len(experiment.candidates), 1)
        stage = experiment.candidates[0].stages[0]
        self.assertEqual(stage.role, "SOLVER")
        self.assertEqual(stage.provider, "openrouter")
        self.assertTrue(stage.prompt.is_absolute())

    def test_task_and_case_default_to_readable_names(self) -> None:
        experiment = self.load(MINIMAL)
        self.assertEqual(experiment.task, {"id": "demo", "version": "1"})
        self.assertEqual(experiment.case, {"id": "fixture", "version": "1"})

    def test_multi_stage_candidate_keeps_order(self) -> None:
        document = MINIMAL + """
  - id: chain
    stages:
      - role: SOLVER
        model: a/model
        prompt: prompts/solve.md
        allow_edit: [docs/report.md]
      - role: REVIEWER
        model: b/model
        prompt: prompts/review.md
        allow_edit: [docs/findings.json]
"""
        experiment = self.load(document)
        chain = experiment.candidate("chain")
        self.assertEqual([item.role for item in chain.stages], ["SOLVER", "REVIEWER"])
        self.assertEqual(chain.stages[1].model, "b/model")

    def test_unknown_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.load(MINIMAL.replace("role: SOLVER", "role: PLANNER"))

    def test_missing_prompt_file_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.load(MINIMAL.replace("prompts/solve.md", "prompts/absent.md"))
        self.assertIn("no prompt", str(caught.exception))

    def test_missing_workspace_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.load(MINIMAL.replace("workspace: fixture", "workspace: absent"))
        self.assertIn("no workspace", str(caught.exception))

    def test_duplicate_candidate_ids_are_rejected(self) -> None:
        document = MINIMAL + """
  - id: single
    stages:
      - role: SOLVER
        model: a/model
        prompt: prompts/solve.md
        allow_edit: [docs/report.md]
"""
        with self.assertRaises(ValueError) as caught:
            self.load(document)
        self.assertIn("unique", str(caught.exception))

    def test_empty_allow_edit_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.load(MINIMAL.replace("allow_edit: [docs/report.md]", "allow_edit: []"))

    def test_unknown_candidate_lookup_reports_the_known_ones(self) -> None:
        experiment = self.load(MINIMAL)
        with self.assertRaises(KeyError) as caught:
            experiment.candidate("absent")
        self.assertIn("single", str(caught.exception))


class VersionedReferenceTests(unittest.TestCase):
    def test_plain_name_gets_version_one(self) -> None:
        self.assertEqual(
            versioned_reference("task-01", "task"), {"id": "task-01", "version": "1"}
        )

    def test_mapping_keeps_its_version(self) -> None:
        self.assertEqual(
            versioned_reference({"id": "t", "version": 3}, "task"),
            {"id": "t", "version": "3"},
        )

    def test_mapping_without_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            versioned_reference({"version": "1"}, "task")


if __name__ == "__main__":
    unittest.main()

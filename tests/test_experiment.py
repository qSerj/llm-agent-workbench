"""Offline tests for reading, editing and writing a short experiment description."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.experiment import (
    dump_experiment,
    experiment_document,
    leading_comment,
    load_experiment,
    parse_experiment,
    reference_field,
    reference_text,
    versioned_reference,
)

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


@unittest.skipUnless(HAS_YAML, "PyYAML is not installed")
class DumpExperimentTests(unittest.TestCase):
    def round_trip(self, document: str):
        holder = make_root(document)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        path = root / "experiment.yaml"
        first = load_experiment(path, root=root)
        text = dump_experiment(first, root=root)
        path.write_text(text, encoding="utf-8")
        return first, load_experiment(path, root=root), text

    def test_written_description_loads_back_the_same(self) -> None:
        first, second, _ = self.round_trip(MINIMAL)
        self.assertEqual(first, second)

    def test_writing_is_stable(self) -> None:
        _, _, text = self.round_trip(MINIMAL)
        holder = make_root(text)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        again = dump_experiment(load_experiment(root / "experiment.yaml", root=root), root=root)
        self.assertEqual(text, again)

    def test_leading_comment_survives(self) -> None:
        comment = "# why this experiment exists\n# and where its numbers live"
        holder = make_root(comment + "\n" + MINIMAL)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        path = root / "experiment.yaml"
        header = leading_comment(path.read_text(encoding="utf-8"))
        self.assertEqual(header, comment)
        text = dump_experiment(load_experiment(path, root=root), root=root, header=header)
        self.assertTrue(text.startswith(comment + "\n\n"))

    def test_repository_description_is_written_back_unchanged(self) -> None:
        """The real file is the format's reference: writing it must be a no-op."""
        path = ROOT / "experiments" / "solver-reviewer-fixer" / "experiment.yaml"
        original = path.read_text(encoding="utf-8")
        experiment = load_experiment(path, root=ROOT)
        written = dump_experiment(
            experiment, root=ROOT, header=leading_comment(original)
        )
        self.assertEqual(original, written)

    def test_workspace_outside_the_root_stays_absolute(self) -> None:
        holder = make_root(MINIMAL)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        experiment = load_experiment(root / "experiment.yaml", root=root)
        experiment.workspace = Path(outside.name)
        self.assertIn(f"workspace: {outside.name}", dump_experiment(experiment, root=root))


class ExperimentDocumentTests(unittest.TestCase):
    """The shell posts flat form fields; they must become a valid description."""

    FIELDS: ClassVar[dict[str, list[str]]] = {
        "id": ["demo"],
        "question": ["Что дешевле?"],
        "workspace": ["fixture"],
        "task": ["task-01"],
        "case": ["fixture@2"],
        "repetitions": ["2"],
        "evaluate.citations": ["docs/report.md"],
        "candidate.0.id": ["single"],
        "candidate.0.stage.0.role": ["solver"],
        "candidate.0.stage.0.model": ["test/model"],
        "candidate.0.stage.0.prompt": ["prompts/solve.md"],
        "candidate.0.stage.0.allow_edit": ["docs/report.md, docs/notes.md"],
    }

    def test_fields_become_a_description(self) -> None:
        document = experiment_document(self.FIELDS)
        self.assertEqual(document["id"], "demo")
        self.assertEqual(document["repetitions"], 2)
        self.assertEqual(document["task"], "task-01")
        self.assertEqual(document["case"], {"id": "fixture", "version": "2"})
        self.assertEqual(document["evaluate"], {"citations": "docs/report.md"})
        stage = document["candidates"][0]["stages"][0]
        self.assertEqual(stage["role"], "SOLVER")
        self.assertEqual(stage["allow_edit"], ["docs/report.md", "docs/notes.md"])
        self.assertNotIn("provider", stage)

    def test_repeated_allow_edit_fields_stay_with_their_own_stage(self) -> None:
        """One input per path: blanks are dropped, and stages do not bleed."""
        fields = dict(self.FIELDS)
        fields["candidate.0.stage.0.allow_edit"] = ["docs/report.md", "", "docs/two.md"]
        fields["candidate.0.stage.1.role"] = ["REVIEWER"]
        fields["candidate.0.stage.1.model"] = ["b/model"]
        fields["candidate.0.stage.1.prompt"] = ["prompts/review.md"]
        fields["candidate.0.stage.1.allow_edit"] = ["docs/findings.json", ""]
        stages = experiment_document(fields)["candidates"][0]["stages"]
        self.assertEqual(stages[0]["allow_edit"], ["docs/report.md", "docs/two.md"])
        self.assertEqual(stages[1]["allow_edit"], ["docs/findings.json"])

    def test_stage_order_follows_the_index_not_the_form_order(self) -> None:
        fields = dict(self.FIELDS)
        fields["candidate.0.stage.10.role"] = ["REVIEWER"]
        fields["candidate.0.stage.10.model"] = ["b/model"]
        fields["candidate.0.stage.10.prompt"] = ["prompts/review.md"]
        fields["candidate.0.stage.10.allow_edit"] = ["docs/findings.json"]
        fields["candidate.0.stage.2.role"] = ["FIXER"]
        fields["candidate.0.stage.2.model"] = ["c/model"]
        fields["candidate.0.stage.2.prompt"] = ["prompts/solve.md"]
        fields["candidate.0.stage.2.allow_edit"] = ["docs/report.md"]
        stages = experiment_document(fields)["candidates"][0]["stages"]
        self.assertEqual([item["role"] for item in stages], ["SOLVER", "FIXER", "REVIEWER"])

    @unittest.skipUnless(HAS_YAML, "PyYAML is not installed")
    def test_a_bad_draft_is_rejected_before_anything_is_written(self) -> None:
        holder = make_root(MINIMAL)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        fields = dict(self.FIELDS)
        fields["candidate.0.stage.0.role"] = ["PLANNER"]
        with self.assertRaises(ValueError):
            parse_experiment(experiment_document(fields), root=root, where="draft")

    @unittest.skipUnless(HAS_YAML, "PyYAML is not installed")
    def test_a_good_draft_parses(self) -> None:
        holder = make_root(MINIMAL)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        experiment = parse_experiment(
            experiment_document(self.FIELDS), root=root, where="draft"
        )
        self.assertEqual(experiment.repetitions, 2)
        self.assertEqual(experiment.case, {"id": "fixture", "version": "2"})


class ReferenceFieldTests(unittest.TestCase):
    def test_version_one_is_written_short(self) -> None:
        self.assertEqual(reference_text({"id": "task-01", "version": "1"}), "task-01")

    def test_other_versions_survive_the_round_trip(self) -> None:
        text = reference_text({"id": "task-01", "version": "3"})
        self.assertEqual(text, "task-01@3")
        self.assertEqual(reference_field(text), {"id": "task-01", "version": "3"})


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

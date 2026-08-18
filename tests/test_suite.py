"""Offline tests for the hidden check suite.

Nothing here needs opencode, a network or a model: the suite under test is a
one-line Python program printing the JSON the mechanism reads.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.chain import StageResult, StageSpec, build_envelope
from workbench.envelope import validate_envelope, verify_artifacts
from workbench.evaluators import attach_all
from workbench.experiment import parse_experiment
from workbench.suite import check_suite_options, run_suite

PASSING = {"checks": [{"id": "one", "outcome": "PASS", "rationale": "ok"}]}
MIXED = {
    "checks": [
        {"id": "one", "outcome": "PASS", "rationale": "ok"},
        {"id": "two", "outcome": "FAIL", "rationale": "дефект на месте"},
    ]
}


def printing(payload: dict) -> list[str]:
    """A suite command that prints one JSON object and nothing else."""
    return [sys.executable, "-c", f"print({json.dumps(json.dumps(payload))})"]


def make_suite(root: Path, name: str = "checks") -> Path:
    suite = root / name
    suite.mkdir(parents=True)
    (suite / "run_checks.py").write_text("# checks live here\n", encoding="utf-8")
    return suite


def make_run(root: Path) -> Path:
    """A stored run with one finished stage, as the chain runner leaves it."""
    source = root / "input-workspace"
    (source / "src").mkdir(parents=True)
    (source / "src" / "Profile.cs").write_text("class Profile {}\n", encoding="utf-8")

    directory = root / "stages" / "1-solver"
    workspace = directory / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "Profile.cs").write_text(
        "class Profile { }\n", encoding="utf-8"
    )
    (directory / "prompt.md").write_text("prompt\n", encoding="utf-8")

    result = StageResult(
        stage_id="1-solver",
        spec=StageSpec(
            role="SOLVER", model="test/model", prompt=Path("p"), allow_edit=["src/*"]
        ),
        directory=directory,
        workspace=workspace,
        model_name="openrouter/test/model",
        exit_code=0,
        wall_seconds=1.0,
        usage={
            "tool_calls": 1,
            "failed_tool_calls": 0,
            "step_finishes": 1,
            "tokens": {"input": 1, "output": 1, "reasoning": 0, "total": 2},
            "api_cost_usd": 0.001,
            "cost_reporting_steps": 1,
        },
    )
    return build_envelope(
        experiment_id="test-experiment",
        candidate_id="chain-v2",
        task={"id": "task-01", "version": "1"},
        case={"id": "fixture", "version": "1"},
        results=[result],
        bundle_root=root,
        source_workspace=source,
        repetition=1,
        started_at="2026-08-18T10:00:00+00:00",
        finished_at="2026-08-18T10:05:00+00:00",
    )


class RunSuiteTests(unittest.TestCase):
    def test_every_check_passing_is_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            result = run_suite(workspace, make_suite(root), printing(PASSING), 60)
            self.assertEqual(result["verdict"], "PASS")
            self.assertEqual(len(result["checks"]), 1)
            self.assertIsNone(result["problem"])

    def test_one_failing_check_fails_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            result = run_suite(workspace, make_suite(root), printing(MIXED), 60)
            self.assertEqual(result["verdict"], "FAIL")
            self.assertEqual([c["outcome"] for c in result["checks"]], ["PASS", "FAIL"])

    def test_unreadable_output_is_undetermined_not_failed(self) -> None:
        """A suite that says nothing readable has established nothing."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            command = [sys.executable, "-c", "print('всё сломалось'); raise SystemExit(1)"]
            result = run_suite(workspace, make_suite(root), command, 60)
            self.assertEqual(result["verdict"], "UNDETERMINED")
            self.assertEqual(result["checks"], [])
            self.assertIn("не разобран", result["problem"])
            self.assertEqual(result["exit_code"], 1)

    def test_an_unknown_outcome_word_becomes_undetermined(self) -> None:
        payload = {"checks": [{"id": "one", "outcome": "GREEN"}]}
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            result = run_suite(workspace, make_suite(root), printing(payload), 60)
            self.assertEqual(result["checks"][0]["outcome"], "UNDETERMINED")
            self.assertEqual(result["verdict"], "UNDETERMINED")

    def test_the_suite_reads_the_workspace_it_is_laid_over(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "answer.txt").write_text("42\n", encoding="utf-8")
            command = [
                sys.executable,
                "-c",
                "import json,pathlib;"
                "text=pathlib.Path('answer.txt').read_text().strip();"
                "print(json.dumps({'checks':[{'id':'answer',"
                "'outcome':'PASS' if text=='42' else 'FAIL','value':text}]}))",
            ]
            result = run_suite(workspace, make_suite(root), command, 60)
            self.assertEqual(result["verdict"], "PASS")
            self.assertEqual(result["checks"][0]["value"], "42")

    def test_the_stored_workspace_keeps_no_trace_of_the_suite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "answer.txt").write_text("42\n", encoding="utf-8")
            run_suite(workspace, make_suite(root), printing(PASSING), 60)
            left = sorted(item.name for item in workspace.iterdir())
            self.assertEqual(left, ["answer.txt"])


class SuiteOptionTests(unittest.TestCase):
    def test_a_suite_inside_the_workspace_is_refused(self) -> None:
        """Isolation is by absence: a suite the executor could read is a mistake."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            suite = make_suite(workspace, "checks")
            with self.assertRaises(ValueError) as caught:
                check_suite_options(
                    {"path": str(suite), "command": ["python3", "run_checks.py"]},
                    root,
                    workspace,
                )
            self.assertIn("исполнитель увидел бы", str(caught.exception))

    def test_a_missing_suite_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaises(ValueError):
                check_suite_options(
                    {"path": "checks", "command": ["python3", "run_checks.py"]},
                    root,
                    None,
                )

    def test_a_command_that_is_not_a_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            make_suite(root)
            with self.assertRaises(ValueError):
                check_suite_options(
                    {"path": "checks", "command": "python3 run_checks.py"}, root, None
                )

    def test_a_description_is_refused_before_it_runs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            (workspace / "src").mkdir(parents=True)
            (root / "prompt.md").write_text("do it\n", encoding="utf-8")
            make_suite(workspace, "checks")
            document = {
                "id": "hidden",
                "question": "виден ли набор исполнителю?",
                "workspace": "workspace",
                "evaluate": {
                    "suite": {
                        "path": "workspace/checks",
                        "command": ["python3", "run_checks.py"],
                    }
                },
                "candidates": [
                    {
                        "id": "one",
                        "stages": [
                            {
                                "role": "SOLVER",
                                "model": "test/model",
                                "prompt": "prompt.md",
                                "allow_edit": ["src/*"],
                            }
                        ],
                    }
                ],
            }
            with self.assertRaises(ValueError) as caught:
                parse_experiment(document, root=root, where="описание")
            self.assertIn("evaluate.suite", str(caught.exception))


class AttachSuiteTests(unittest.TestCase):
    def test_the_card_records_which_suite_measured_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope = make_run(root)
            suite = make_suite(root / "reference")
            attach_all(
                envelope,
                root,
                {"suite": {"path": str(suite), "command": printing(MIXED)}},
            )
            validate_envelope(envelope)
            verify_artifacts(envelope, root)

            evaluation = envelope["evaluations"][0]
            self.assertEqual(evaluation["id"], "suite")
            self.assertEqual(evaluation["evaluator"]["source"], "CODE")
            self.assertEqual(evaluation["result"]["verdict"], "FAIL")
            self.assertEqual(evaluation["subject"]["id"], "1-solver-workspace")

            artifacts = {item["id"]: item for item in envelope["artifacts"]}
            self.assertEqual(artifacts["check-suite"]["role"], "EVIDENCE")
            self.assertEqual(
                artifacts["check-suite"]["digest_method"], "sha256-tree-manifest-v1"
            )
            self.assertEqual(artifacts["check-suite-output"]["role"], "LOG")
            self.assertEqual(
                sorted(evaluation["evidence_artifact_ids"]),
                ["check-suite", "check-suite-output"],
            )

    def test_evaluating_twice_replaces_rather_than_accumulates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope = make_run(root)
            suite = make_suite(root / "reference")
            options = {"suite": {"path": str(suite), "command": printing(MIXED)}}
            attach_all(envelope, root, options)
            attach_all(envelope, root, options)
            validate_envelope(envelope)
            verify_artifacts(envelope, root)
            self.assertEqual(len(envelope["evaluations"]), 1)
            ids = [item["id"] for item in envelope["artifacts"]]
            self.assertEqual(ids.count("check-suite"), 1)

    def test_the_run_workspace_is_left_without_check_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope = make_run(root)
            suite = make_suite(root / "reference")
            attach_all(
                envelope,
                root,
                {"suite": {"path": str(suite), "command": printing(PASSING)}},
            )
            workspace = root / "stages" / "1-solver" / "workspace"
            present = {item.name for item in workspace.rglob("*")}
            self.assertNotIn("run_checks.py", present)
            # The card's own checksum agrees: the stored run did not change.
            verify_artifacts(envelope, root)


if __name__ == "__main__":
    unittest.main()

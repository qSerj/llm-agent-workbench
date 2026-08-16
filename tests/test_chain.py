"""Offline tests for multi-stage candidate assembly."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.chain import (
    StageResult,
    StageSpec,
    build_envelope,
    collect_usage_from_jsonl,
    permission_config,
    total_cost,
)
from workbench.envelope import validate_envelope, verify_artifacts


def make_stage(
    root: Path, index: int, role: str, cost: float | None, wall: float
) -> StageResult:
    """Create a stage directory that looks like a finished OpenCode run."""
    directory = root / "stages" / f"{index}-{role.lower()}"
    workspace = directory / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "docs" / "01-interleavers.md").write_text(
        f"# stage {index}\n", encoding="utf-8"
    )
    (directory / "prompt.md").write_text(f"prompt {index}\n", encoding="utf-8")
    (directory / "opencode.jsonl").write_text("", encoding="utf-8")
    (directory / "git.diff").write_text("", encoding="utf-8")
    (directory / "exit.json").write_text("{}", encoding="utf-8")
    return StageResult(
        stage_id=f"{index}-{role.lower()}",
        spec=StageSpec(
            role=role, model="test/model", prompt=Path("p"), allow_edit=["docs/x.md"]
        ),
        directory=directory,
        workspace=workspace,
        model_name="openrouter/test/model",
        exit_code=0,
        wall_seconds=wall,
        usage={
            "tool_calls": 3,
            "failed_tool_calls": 1,
            "step_finishes": 2,
            "tokens": {"input": 10, "output": 5, "reasoning": 0, "total": 15},
            "api_cost_usd": cost,
            "cost_reporting_steps": 2 if cost is not None else 0,
        },
    )


def build(root: Path, costs: list[float | None]) -> dict:
    source = root / "input-workspace"
    (source / "src").mkdir(parents=True)
    (source / "src" / "Profile.cs").write_text("class Profile {}\n", encoding="utf-8")
    roles = ["SOLVER", "REVIEWER", "FIXER"]
    results = [
        make_stage(root, index, roles[index - 1], cost, wall=float(index) * 10.0)
        for index, cost in enumerate(costs, start=1)
    ]
    return build_envelope(
        experiment_id="test-experiment",
        candidate_id="chain-v2",
        task={"id": "task-01", "version": "1"},
        case={"id": "interleaver-fixture", "version": "1"},
        results=results,
        bundle_root=root,
        source_workspace=source,
        repetition=1,
        started_at="2026-08-16T10:00:00+00:00",
        finished_at="2026-08-16T10:05:00+00:00",
    )


class ChainEnvelopeTests(unittest.TestCase):
    def test_three_stage_chain_is_valid_and_wired(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope = build(root, [0.001, 0.002, 0.003])
            validate_envelope(envelope)
            verify_artifacts(envelope, root)

            stages = envelope["stages"]
            self.assertEqual([item["id"] for item in stages], [
                "1-solver", "2-reviewer", "3-fixer"
            ])
            self.assertEqual(stages[0]["depends_on"], [])
            self.assertEqual(stages[1]["depends_on"], ["1-solver"])
            self.assertEqual(stages[2]["depends_on"], ["2-reviewer"])
            self.assertEqual(stages[0]["input_artifact_ids"], ["input-workspace"])
            self.assertEqual(
                stages[1]["input_artifact_ids"], stages[0]["output_artifact_ids"]
            )

    def test_every_stage_measurement_names_a_real_stage(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope = build(root, [0.001, 0.002, 0.003])
            stage_ids = {item["id"] for item in envelope["stages"]}
            attributed = [
                item for item in envelope["observations"] if "stage_id" in item
            ]
            self.assertTrue(attributed)
            for item in attributed:
                self.assertIn(item["stage_id"], stage_ids)

            costs = [
                item["value"]
                for item in attributed
                if item["name"] == "api_cost"
            ]
            self.assertEqual(costs, [0.001, 0.002, 0.003])

    def test_unknown_stage_cost_makes_the_total_unknown(self) -> None:
        """A partial sum shown as a total would understate the candidate."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope = build(root, [0.001, None, 0.003])
            validate_envelope(envelope)
            total = next(
                item
                for item in envelope["observations"]
                if item["name"] == "api_cost" and "stage_id" not in item
            )
            self.assertIsNone(total["value"])

    def test_total_cost_is_none_when_any_stage_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            results = [
                make_stage(root, 1, "SOLVER", 0.5, 1.0),
                make_stage(root, 2, "REVIEWER", None, 1.0),
            ]
            self.assertIsNone(total_cost(results))
            self.assertEqual(total_cost(results[:1]), 0.5)


class StagePermissionTests(unittest.TestCase):
    def test_only_declared_paths_are_editable(self) -> None:
        config = permission_config(["docs/01.md", "docs/review-findings.json"])
        self.assertEqual(config["edit"]["*"], "deny")
        self.assertEqual(config["edit"]["docs/01.md"], "allow")
        self.assertEqual(config["edit"]["docs/review-findings.json"], "allow")

    def test_traversal_and_globs_are_rejected(self) -> None:
        for path in ("../escape.md", "/etc/passwd", "docs/*.md", "docs/?.md"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                permission_config([path])

    def test_a_stage_must_declare_something(self) -> None:
        with self.assertRaises(ValueError):
            permission_config([])


class UsageTests(unittest.TestCase):
    def write_log(self, directory: Path, events: list[dict]) -> Path:
        path = directory / "opencode.jsonl"
        path.write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
        return path

    def test_costs_and_tool_failures_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = self.write_log(
                Path(raw),
                [
                    {"type": "tool_use", "part": {"state": {"status": "completed"}}},
                    {"type": "tool_use", "part": {"state": {"status": "error"}}},
                    {
                        "type": "step_finish",
                        "part": {
                            "cost": 0.25,
                            "tokens": {"input": 100, "output": 20, "total": 120},
                        },
                    },
                    {"type": "step_finish", "part": {"cost": 0.25}},
                ],
            )
            usage = collect_usage_from_jsonl(path)
            self.assertEqual(usage["tool_calls"], 2)
            self.assertEqual(usage["failed_tool_calls"], 1)
            self.assertEqual(usage["api_cost_usd"], 0.5)
            self.assertEqual(usage["tokens"]["input"], 100)

    def test_silence_about_cost_stays_unknown(self) -> None:
        """A local endpoint reports no price; that is not a price of zero."""
        with tempfile.TemporaryDirectory() as raw:
            path = self.write_log(
                Path(raw),
                [{"type": "step_finish", "part": {"tokens": {"total": 10}}}],
            )
            usage = collect_usage_from_jsonl(path)
            self.assertIsNone(usage["api_cost_usd"])
            self.assertEqual(usage["cost_reporting_steps"], 0)

    def test_malformed_lines_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "opencode.jsonl"
            path.write_text(
                'not json\n{"type": "tool_use", "part": {}}\n[partial\n',
                encoding="utf-8",
            )
            self.assertEqual(collect_usage_from_jsonl(path)["tool_calls"], 1)


if __name__ == "__main__":
    unittest.main()

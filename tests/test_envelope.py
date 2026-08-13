import copy
import json
import tempfile
import unittest
from pathlib import Path

from workbench.envelope import (
    build_legacy_opencode_envelope,
    validate_envelope,
    verify_artifacts,
)


def make_bundle(root: Path, returncode=0, document="# Useful output\n"):
    root = root / "20260813_100000_provider_model"
    task = root / "task01"
    docs = task / "workspace" / "docs"
    docs.mkdir(parents=True)
    source = task / "workspace" / "src"
    source.mkdir()
    (source / "Example.cs").write_text(
        "public sealed class Example {}\n", encoding="utf-8"
    )
    generated = source / "obj"
    generated.mkdir()
    (generated / "machine-specific.cache").write_text("ignored\n", encoding="utf-8")
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "runner_version": "test-r1",
                "timestamp": "20260813_100000",
                "provider": "compatible",
                "model": "test-model",
                "context": 4096,
            }
        ),
        encoding="utf-8",
    )
    (task / "exit.json").write_text(
            json.dumps(
                {
                    "returncode": returncode,
                    "wall_seconds": 1.5,
                    "tool_calls": 2,
                    "failed_tool_calls": 0,
                    "summed_step_tokens": None,
                    "total_reported_cost_usd": None,
                    "estimated_kwh": None,
                }
            ),
            encoding="utf-8",
    )
    (task / "grade.json").write_text(
            json.dumps(
                {
                    "task": 1,
                    "score": 1 if returncode == 0 else 0,
                    "max_score": 1,
                    "checks": [
                        {
                            "name": "document",
                            "ok": returncode == 0,
                            "points": 1 if returncode == 0 else 0,
                            "max_points": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
    )
    (task / "prompt.md").write_text("Write documentation.\n", encoding="utf-8")
    (task / "opencode.jsonl").write_text(
        '{"type":"step_finish"}\n', encoding="utf-8"
    )
    (task / "effective_model.txt").write_text("test/model\n", encoding="utf-8")
    (docs / "01-interleavers.md").write_text(document, encoding="utf-8")
    return task


class LegacyEnvelopeTests(unittest.TestCase):
    def make_bundle(self, returncode=0, document="# Useful output\n"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return make_bundle(Path(temporary.name), returncode, document)

    def test_builds_and_validates_success(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle())

        validate_envelope(envelope)

        self.assertEqual(envelope["lifecycle"]["status"], "SUCCEEDED")
        self.assertEqual(envelope["evaluations"][0]["result"]["verdict"], "PASS")
        source_tree = next(
            item for item in envelope["artifacts"] if item["id"] == "source-tree"
        )
        self.assertEqual(source_tree["content_kind"], "DIRECTORY")
        self.assertEqual(source_tree["digest_method"], "sha256-tree-manifest-v1")
        self.assertEqual(source_tree["exclusions"], ["bin", "obj"])
        self.assertEqual(envelope["case"]["version"], f"sha256:{source_tree['sha256']}")
        self.assertTrue(envelope["task"]["version"].startswith("sha256:"))
        self.assertNotIn(
            "api_cost", {item["name"] for item in envelope["observations"]}
        )

    def test_nonzero_execution_with_output_is_partial(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle(returncode=7))

        validate_envelope(envelope)

        self.assertEqual(envelope["lifecycle"]["status"], "PARTIAL")
        self.assertEqual(envelope["evaluations"][0]["result"]["verdict"], "FAIL")

    def test_nonzero_execution_without_output_is_failed_but_valid(self):
        task = self.make_bundle(returncode=9)
        (task / "workspace" / "docs" / "01-interleavers.md").unlink()

        envelope = build_legacy_opencode_envelope(task)
        validate_envelope(envelope)

        self.assertEqual(envelope["lifecycle"]["status"], "FAILED")
        self.assertNotIn("generated-document", {item["id"] for item in envelope["artifacts"]})

    def test_verifies_artifacts_and_detects_changed_output(self):
        task = self.make_bundle()
        envelope = build_legacy_opencode_envelope(task)

        verify_artifacts(envelope, task.parent)
        (task / "workspace" / "docs" / "01-interleavers.md").write_text(
            "changed\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "artifact content mismatch"):
            verify_artifacts(envelope, task.parent)

    def test_human_assessment_must_match_output_hash(self):
        task = self.make_bundle()
        assessment = task.parent / "assessment.json"
        assessment.write_text(
            json.dumps(
                {
                    "subject_sha256": "0" * 64,
                    "id": "human-test",
                    "subject": {"kind": "ARTIFACT", "id": "generated-document"},
                    "evaluator": {"source": "HUMAN", "identity": "reviewer"},
                    "policy": {"id": "review", "version": "1"},
                    "result": {"verdict": "PASS"},
                    "rationale": "Looks useful.",
                    "evidence_artifact_ids": ["generated-document"],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "subject hash"):
            build_legacy_opencode_envelope(task, assessment)

    def test_rejects_unknown_evidence_artifact(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle())
        invalid = copy.deepcopy(envelope)
        invalid["evaluations"][0]["evidence_artifact_ids"] = ["missing"]

        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_envelope(invalid)

    def test_rejects_dimension_outside_declared_scale(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle())
        invalid = copy.deepcopy(envelope)
        invalid["evaluations"][0]["result"]["dimensions"] = [
            {
                "id": "quality",
                "value": 3,
                "scale": {
                    "minimum": 0,
                    "maximum": 2,
                    "direction": "HIGHER_IS_BETTER",
                    "anchors": {"0": "bad", "2": "good"},
                },
            }
        ]

        with self.assertRaisesRegex(ValueError, "outside scale"):
            validate_envelope(invalid)

    def test_validates_stage_artifact_and_dependency_links(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle())
        envelope["stages"] = [
            {
                "id": "solver",
                "role": "SOLVER",
                "execution_id": "child:solver",
                "depends_on": [],
                "input_artifact_ids": ["task-prompt", "source-tree"],
                "output_artifact_ids": ["generated-document"],
            },
            {
                "id": "reviewer",
                "role": "REVIEWER",
                "execution_id": "child:reviewer",
                "depends_on": ["solver"],
                "input_artifact_ids": ["generated-document", "source-tree"],
                "output_artifact_ids": ["grader-output"],
            },
        ]
        envelope["observations"][0]["stage_id"] = "solver"

        validate_envelope(envelope)

    def test_rejects_stage_dependency_cycle(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle())
        envelope["stages"] = [
            {
                "id": "solver",
                "role": "SOLVER",
                "execution_id": "child:solver",
                "depends_on": ["reviewer"],
                "input_artifact_ids": [],
                "output_artifact_ids": [],
            },
            {
                "id": "reviewer",
                "role": "REVIEWER",
                "execution_id": "child:reviewer",
                "depends_on": ["solver"],
                "input_artifact_ids": [],
                "output_artifact_ids": [],
            },
        ]

        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            validate_envelope(envelope)

    def test_rejects_unknown_stage_artifact_and_observation_stage(self):
        envelope = build_legacy_opencode_envelope(self.make_bundle())
        envelope["stages"] = [
            {
                "id": "solver",
                "role": "SOLVER",
                "execution_id": "child:solver",
                "depends_on": [],
                "input_artifact_ids": ["missing"],
                "output_artifact_ids": [],
            }
        ]
        with self.assertRaisesRegex(ValueError, "unknown stage artifacts"):
            validate_envelope(envelope)

        envelope["stages"][0]["input_artifact_ids"] = []
        envelope["observations"][0]["stage_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown observation stage"):
            validate_envelope(envelope)


if __name__ == "__main__":
    unittest.main()

import copy
import tempfile
import unittest
from pathlib import Path

from workbench.envelope import (
    directory_artifact,
    file_artifact,
    validate_envelope,
    verify_artifacts,
)


def make_envelope(root: Path) -> dict:
    input_path = root / "input.txt"
    output_path = root / "output.txt"
    input_path.write_text("question\n", encoding="utf-8")
    output_path.write_text("answer\n", encoding="utf-8")
    return {
        "schema_version": "1.0",
        "execution_id": "test:execution:1",
        "task": {"id": "transform", "version": "1"},
        "case": {"id": "small-input", "version": "1"},
        "candidate": {"id": "example-program", "version": "1"},
        "repetition": 1,
        "lifecycle": {
            "status": "SUCCEEDED",
            "started_at": "2026-08-13T10:00:00+00:00",
            "finished_at": "2026-08-13T10:00:01+00:00",
            "timestamp_basis": "utc-system-clock",
        },
        "executor": {
            "implementation": "example-program",
            "version": "1",
            "exit_code": 0,
        },
        "artifacts": [
            file_artifact("input", "INPUT", input_path, root, "text/plain"),
            file_artifact("output", "OUTPUT", output_path, root, "text/plain"),
        ],
        "stages": [
            {
                "id": "transform",
                "role": "OTHER",
                "execution_id": "test:stage:1",
                "depends_on": [],
                "input_artifact_ids": ["input"],
                "output_artifact_ids": ["output"],
            }
        ],
        "observations": [
            {
                "name": "wall_time",
                "value": 1.0,
                "unit": "s",
                "method": "monotonic-clock",
                "stage_id": "transform",
            }
        ],
        "evaluations": [
            {
                "id": "output-check",
                "subject": {"kind": "ARTIFACT", "id": "output"},
                "evaluator": {"source": "CODE", "identity": "test-check"},
                "policy": {"id": "nonempty-output", "version": "1"},
                "result": {"verdict": "PASS"},
                "rationale": "The output is non-empty.",
                "evidence_artifact_ids": ["output"],
            }
        ],
        "correlations": [],
    }


class EnvelopeTests(unittest.TestCase):
    def make_bundle(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        return root, make_envelope(root)

    def test_validates_and_verifies_generic_execution(self):
        root, envelope = self.make_bundle()
        validate_envelope(envelope)
        verify_artifacts(envelope, root)

    def test_detects_changed_artifact(self):
        root, envelope = self.make_bundle()
        (root / "output.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact content mismatch"):
            verify_artifacts(envelope, root)

    def test_directory_digest_ignores_declared_generated_directory(self):
        root, envelope = self.make_bundle()
        source = root / "source"
        source.mkdir()
        (source / "data.txt").write_text("stable\n", encoding="utf-8")
        generated = source / "generated"
        generated.mkdir()
        (generated / "cache.bin").write_bytes(b"first")
        envelope["artifacts"].append(
            directory_artifact(
                "source-tree",
                "INPUT",
                source,
                root,
                "application/vnd.workbench.directory",
                frozenset({"generated"}),
            )
        )

        (generated / "cache.bin").write_bytes(b"second")
        validate_envelope(envelope)
        verify_artifacts(envelope, root)

        (source / "data.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact content mismatch"):
            verify_artifacts(envelope, root)

    def test_partial_and_failed_are_valid_execution_states(self):
        _, envelope = self.make_bundle()
        for status in ("PARTIAL", "FAILED"):
            candidate = copy.deepcopy(envelope)
            candidate["lifecycle"]["status"] = status
            candidate["executor"]["exit_code"] = 1
            validate_envelope(candidate)

    def test_rejects_unknown_evidence_artifact(self):
        _, envelope = self.make_bundle()
        envelope["evaluations"][0]["evidence_artifact_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_envelope(envelope)

    def test_rejects_dimension_outside_declared_scale(self):
        _, envelope = self.make_bundle()
        envelope["evaluations"][0]["result"]["dimensions"] = [
            {
                "id": "quality",
                "value": 11,
                "scale": {
                    "minimum": 0,
                    "maximum": 10,
                    "direction": "HIGHER_IS_BETTER",
                    "anchors": {"0": "bad", "10": "good"},
                },
            }
        ]
        with self.assertRaisesRegex(ValueError, "outside scale"):
            validate_envelope(envelope)

    def test_rejects_stage_dependency_cycle(self):
        _, envelope = self.make_bundle()
        envelope["stages"].append(
            {
                "id": "review",
                "role": "REVIEWER",
                "execution_id": "test:stage:2",
                "depends_on": ["transform"],
                "input_artifact_ids": ["output"],
                "output_artifact_ids": [],
            }
        )
        envelope["stages"][0]["depends_on"] = ["review"]
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            validate_envelope(envelope)

    def test_rejects_unknown_stage_links(self):
        _, envelope = self.make_bundle()
        invalid_artifact = copy.deepcopy(envelope)
        invalid_artifact["stages"][0]["input_artifact_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown stage artifacts"):
            validate_envelope(invalid_artifact)

        envelope["observations"][0]["stage_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown observation stage"):
            validate_envelope(envelope)


if __name__ == "__main__":
    unittest.main()

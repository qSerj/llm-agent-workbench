"""Offline tests for the deterministic citation check."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.citations import check_citations, citation_evaluation
from workbench.envelope import validate_envelope


def workspace_with(document_text: str, source_lines: int) -> tempfile.TemporaryDirectory:
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name)
    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "Example.cs").write_text(
        "".join(f"// line {number}\n" for number in range(1, source_lines + 1)),
        encoding="utf-8",
    )
    (root / "docs" / "report.md").write_text(document_text, encoding="utf-8")
    return holder


class CitationTests(unittest.TestCase):
    def test_citation_inside_the_file_passes(self) -> None:
        with workspace_with("See `src/Example.cs:5` for details.\n", 10) as raw:
            result = check_citations(Path(raw) / "docs" / "report.md", Path(raw))
            self.assertEqual(result["verdict"], "PASS")
            self.assertEqual(len(result["checks"]), 1)

    def test_citation_past_the_end_of_the_file_fails(self) -> None:
        """The exact regression a perfect grader once missed."""
        with workspace_with("See `src/Example.cs:11` for details.\n", 10) as raw:
            result = check_citations(Path(raw) / "docs" / "report.md", Path(raw))
            self.assertEqual(result["verdict"], "FAIL")
            self.assertEqual(result["checks"][0]["outcome"], "FAIL")
            self.assertIn("past the end", result["checks"][0]["rationale"])

    def test_missing_file_fails(self) -> None:
        with workspace_with("See `src/Absent.cs:1`.\n", 10) as raw:
            result = check_citations(Path(raw) / "docs" / "report.md", Path(raw))
            self.assertEqual(result["verdict"], "FAIL")
            self.assertIn("missing", result["checks"][0]["rationale"])

    def test_document_without_citations_is_undetermined(self) -> None:
        """Nothing to verify is not the same as verified, nor as broken."""
        with workspace_with("A report with no citations at all.\n", 10) as raw:
            result = check_citations(Path(raw) / "docs" / "report.md", Path(raw))
            self.assertEqual(result["verdict"], "UNDETERMINED")
            self.assertEqual(result["checks"], [])

    def test_one_broken_citation_fails_the_whole_document(self) -> None:
        text = "Good `src/Example.cs:3`, bad `src/Example.cs:99`.\n"
        with workspace_with(text, 10) as raw:
            result = check_citations(Path(raw) / "docs" / "report.md", Path(raw))
            self.assertEqual(result["verdict"], "FAIL")
            outcomes = [item["outcome"] for item in result["checks"]]
            self.assertEqual(outcomes, ["PASS", "FAIL"])


class CitationEvaluationTests(unittest.TestCase):
    def test_evaluation_is_a_valid_code_evaluation(self) -> None:
        with workspace_with("See `src/Example.cs:11`.\n", 10) as raw:
            root = Path(raw)
            document = root / "docs" / "report.md"
            evaluation = citation_evaluation(
                "citations", document, root, "final-document", ["final-document"]
            )
            self.assertEqual(evaluation["evaluator"]["source"], "CODE")
            self.assertEqual(evaluation["result"]["verdict"], "FAIL")
            self.assertIn("Example.cs:11", evaluation["rationale"])

            envelope = {
                "schema_version": "1.0",
                "execution_id": "e1",
                "task": {"id": "t", "version": "1"},
                "case": {"id": "c", "version": "1"},
                "candidate": {"id": "k", "version": "1"},
                "repetition": 1,
                "lifecycle": {
                    "status": "SUCCEEDED",
                    "started_at": "2026-08-16T10:00:00+00:00",
                    "finished_at": "2026-08-16T10:01:00+00:00",
                    "timestamp_basis": "UTC system clock",
                },
                "executor": {
                    "implementation": "test",
                    "version": "1",
                    "exit_code": 0,
                },
                "artifacts": [
                    {
                        "id": "final-document",
                        "role": "OUTPUT",
                        "content_kind": "FILE",
                        "media_type": "text/markdown",
                        "byte_size": document.stat().st_size,
                        "sha256": "0" * 64,
                        "digest_method": "sha256-file-bytes",
                        "location": {"path": "docs/report.md"},
                    }
                ],
                "observations": [],
                "evaluations": [evaluation],
                "correlations": [],
            }
            validate_envelope(envelope)


if __name__ == "__main__":
    unittest.main()

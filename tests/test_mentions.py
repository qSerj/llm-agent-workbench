"""Offline tests for the reverse check: does a mentioned name exist at all?

The fixture used is the one in the repository, so the material is the same the
runs of 2026-08-13 worked over.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.envelope import validate_envelope
from workbench.mentions import check_mentions, mentioned_names, mentions_evaluation

FIXTURE = ROOT / "experiments" / "solver-reviewer-fixer" / "workspace"


def document_in(directory: str, text: str) -> Path:
    path = Path(directory) / "report.md"
    path.write_text(text, encoding="utf-8")
    return path


class MentionedNamesTests(unittest.TestCase):
    def names(self, text: str) -> list[str]:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return mentioned_names(document_in(holder.name, text), "csharp")

    def test_only_marked_code_is_read(self) -> None:
        """Prose is not scanned: a name must be marked as code to be a claim."""
        self.assertEqual(self.names("Класс SimpleInterleaverProfile хорош.\n"), [])
        self.assertEqual(
            self.names("Класс `SimpleInterleaverProfile` хорош.\n"),
            ["SimpleInterleaverProfile"],
        )

    def test_a_fenced_example_is_read_too(self) -> None:
        """The invention of 2026-08-13 lived in a usage example, not in a span."""
        text = "Пример:\n\n```csharp\nvar t = new TableInterleaverProfile(d);\n```\n"
        self.assertEqual(self.names(text), ["TableInterleaverProfile"])

    def test_a_citation_path_is_left_to_the_citation_check(self) -> None:
        self.assertEqual(self.names("См. `src/Interleaver.Core/Absent.cs:3`.\n"), [])

    def test_all_lower_case_words_are_not_claimed(self) -> None:
        """A shallow reading that says what it misses is honest."""
        self.assertEqual(self.names("Тип `int` и поле `delays`.\n"), [])
        # A camel-case parameter does carry a capital, and is a claim.
        self.assertEqual(self.names("Параметр `branchCount`.\n"), ["branchCount"])


class CheckMentionsTests(unittest.TestCase):
    def document(self, text: str) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return document_in(holder.name, text)

    def check(self, text: str) -> dict:
        return check_mentions(self.document(text), FIXTURE, "csharp")

    def test_names_that_exist_pass(self) -> None:
        result = self.check("`SimpleInterleaverProfile.ToRegisters()` даёт регистры.\n")
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(
            sorted(item["id"] for item in result["checks"]),
            ["SimpleInterleaverProfile", "ToRegisters"],
        )

    def test_the_invented_method_of_2026_08_13_is_caught(self) -> None:
        """`WriteRegisters` never existed; the real member is `WriteAsync`."""
        result = self.check(
            "Транспорт вызывается через `IRegisterTransport.WriteRegisters()`.\n"
        )
        self.assertEqual(result["verdict"], "FAIL")
        invented = [c["id"] for c in result["checks"] if c["outcome"] == "FAIL"]
        self.assertEqual(invented, ["WriteRegisters"])
        supported = [c for c in result["checks"] if c["id"] == "IRegisterTransport"]
        self.assertEqual(supported[0]["outcome"], "PASS")
        self.assertGreater(supported[0]["value"], 0)

    def test_a_document_naming_no_code_is_undetermined(self) -> None:
        """Nothing claimed is not the same as nothing invented."""
        result = self.check("Документ без единого имени кода.\n")
        self.assertEqual(result["verdict"], "UNDETERMINED")
        self.assertEqual(result["checks"], [])

    def test_sources_that_are_not_there_leave_the_question_open(self) -> None:
        path = self.document("`SimpleInterleaverProfile` существует.\n")
        with tempfile.TemporaryDirectory() as empty:
            result = check_mentions(path, Path(empty), "csharp")
        self.assertEqual(result["verdict"], "UNDETERMINED")

    def test_an_unknown_language_is_refused(self) -> None:
        path = self.document("`Foo`.\n")
        with self.assertRaises(ValueError):
            check_mentions(path, FIXTURE, "rust")


class MentionsEvaluationTests(unittest.TestCase):
    def test_the_evaluation_is_a_valid_code_evaluation(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        path = document_in(holder.name, "Вызов `IRegisterTransport.WriteRegisters()`.\n")
        evaluation = mentions_evaluation(
            "mentions", path, FIXTURE, "csharp", "final-document", ["final-document"]
        )
        self.assertEqual(evaluation["evaluator"]["source"], "CODE")
        self.assertEqual(evaluation["result"]["verdict"], "FAIL")
        self.assertIn("WriteRegisters", evaluation["rationale"])

        envelope = {
            "schema_version": "1.0",
            "execution_id": "e1",
            "task": {"id": "t", "version": "1"},
            "case": {"id": "c", "version": "1"},
            "candidate": {"id": "k", "version": "1"},
            "repetition": 1,
            "lifecycle": {
                "status": "SUCCEEDED",
                "started_at": "2026-08-18T10:00:00+00:00",
                "finished_at": "2026-08-18T10:01:00+00:00",
                "timestamp_basis": "UTC system clock",
            },
            "executor": {"implementation": "test", "version": "1", "exit_code": 0},
            "artifacts": [
                {
                    "id": "final-document",
                    "role": "OUTPUT",
                    "content_kind": "FILE",
                    "media_type": "text/markdown",
                    "byte_size": path.stat().st_size,
                    "sha256": "0" * 64,
                    "digest_method": "sha256-file-bytes",
                    "location": {"path": "report.md"},
                }
            ],
            "observations": [],
            "evaluations": [evaluation],
            "correlations": [],
        }
        validate_envelope(envelope)


if __name__ == "__main__":
    unittest.main()

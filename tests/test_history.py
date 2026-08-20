"""Offline tests for exporting the project's history as wiki sources.

Nothing here needs a network or a model. The git-backed exports run against a
disposable repository created in a temporary directory, so the tests say
nothing about this repository's actual commits.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.history import (
    document_name,
    export_commits,
    export_conversations,
    export_documents,
    slugify,
    spoken_turn,
    write_manifest,
)


def make_repository(root: Path) -> None:
    """A tiny git repository with one document and one commit."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "Test")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    (root / "VISION.md").write_text("# Замысел\n\nПервая версия.\n", encoding="utf-8")
    (root / "docs" / "decisions").mkdir(parents=True)
    (root / "docs" / "decisions" / "0003-portable-envelope.md").write_text(
        "# ADR 0003\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", "Record the first idea"], check=True
    )


def write_transcript(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def turn(kind: str, content, day: str = "2026-08-20", **extra) -> dict:
    return {
        "type": kind,
        "message": {"content": content},
        "timestamp": f"{day}T10:00:00.000Z",
        "isSidechain": False,
        **extra,
    }


class SlugTests(unittest.TestCase):
    def test_truncation_stops_at_a_word_boundary(self) -> None:
        name = slugify("archive prototype docs decisions research before production", limit=30)
        self.assertLessEqual(len(name), 30)
        self.assertFalse(name.endswith("-"))
        # The cut lands between words, not inside one.
        self.assertNotIn("producti", name)

    def test_cyrillic_survives_and_yo_is_folded(self) -> None:
        self.assertEqual(slugify("Приём источника"), "прием-источника")

    def test_a_name_with_nothing_usable_still_has_one(self) -> None:
        self.assertEqual(slugify("!!! ???"), "untitled")


class DocumentNameTests(unittest.TestCase):
    def test_a_decision_is_named_as_an_adr(self) -> None:
        name = document_name(Path("docs/decisions/0006-shell-and-chains.md"))
        self.assertEqual(name, "adr-0006-shell-and-chains.md")

    def test_the_archive_keeps_its_prefix(self) -> None:
        name = document_name(Path("archive/prototype-r4.2/docs/decisions/0001-research.md"))
        self.assertEqual(name, "archive-adr-0001-research.md")

    def test_a_plain_document_keeps_its_own_name(self) -> None:
        self.assertEqual(document_name(Path("VISION.md")), "vision.md")


class SpokenTurnTests(unittest.TestCase):
    def test_a_person_speaking_is_kept(self) -> None:
        day, text = spoken_turn(turn("user", "продолжаем работу"))
        self.assertEqual(day, "2026-08-20")
        self.assertIn("### Владелец", text)
        self.assertIn("продолжаем работу", text)

    def test_a_compaction_summary_is_not_a_turn(self) -> None:
        record = turn("user", "This session is being continued…", isCompactSummary=True)
        self.assertIsNone(spoken_turn(record))

    def test_a_bare_slash_command_is_not_a_turn(self) -> None:
        self.assertIsNone(spoken_turn(turn("user", "/compact")))

    def test_a_slash_that_starts_a_real_message_is_kept(self) -> None:
        long_enough = "/loop " + "надо повторять проверку каждые пять минут " * 6
        self.assertIsNotNone(spoken_turn(turn("user", long_enough)))

    def test_a_tool_only_reply_is_dropped(self) -> None:
        content = [{"type": "tool_use", "name": "Bash", "input": {}}]
        self.assertIsNone(spoken_turn(turn("assistant", content)))

    def test_prose_next_to_a_tool_call_is_kept(self) -> None:
        content = [
            {"type": "text", "text": "Смотрю историю."},
            {"type": "tool_use", "name": "Bash", "input": {}},
        ]
        result = spoken_turn(turn("assistant", content))
        self.assertIsNotNone(result)
        self.assertIn("Смотрю историю.", result[1])

    def test_tool_results_never_become_text(self) -> None:
        content = [{"type": "tool_result", "content": "секретный вывод команды"}]
        self.assertIsNone(spoken_turn(turn("user", content)))

    def test_a_subagent_turn_is_not_the_conversation(self) -> None:
        record = turn("assistant", [{"type": "text", "text": "подзадача"}])
        record["isSidechain"] = True
        self.assertIsNone(spoken_turn(record))

    def test_injected_context_is_stripped(self) -> None:
        record = turn("user", "<system-reminder>служебное</system-reminder>\nвопрос по делу")
        _, text = spoken_turn(record)
        self.assertNotIn("служебное", text)
        self.assertIn("вопрос по делу", text)


class ExportTests(unittest.TestCase):
    def test_documents_and_commits_land_with_a_verifiable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repo"
            repository.mkdir()
            make_repository(repository)
            output = Path(directory) / "raw"

            entries = export_documents(repository, output)
            entries += export_commits(repository, output, diff_limit=10_000)
            manifest_path = write_manifest(repository, output, entries)

            names = {entry["path"] for entry in entries}
            self.assertIn("documents/vision.md", names)
            self.assertIn("documents/adr-0003-portable-envelope.md", names)
            self.assertTrue(any(name.startswith("commits/") for name in names))

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["digest_method"], "sha256-file-bytes")
            for entry in manifest["sources"]:
                path = output / entry["path"]
                self.assertTrue(path.is_file(), entry["path"])
                self.assertEqual(path.stat().st_size, entry["bytes"])

            # The whole point of the export: what a source came from stays
            # attached to it, so a wiki page can cite the original.
            vision = next(e for e in entries if e["path"] == "documents/vision.md")
            self.assertEqual(vision["origin"], "VISION.md")
            self.assertIn("Первая версия", (output / vision["path"]).read_text(encoding="utf-8"))

    def test_an_oversized_diff_is_marked_as_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repo"
            repository.mkdir()
            make_repository(repository)
            (repository / "big.txt").write_text("строка\n" * 4000, encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-q", "-m", "Add a large file"],
                check=True,
            )
            output = Path(directory) / "raw"

            entries = export_commits(repository, output, diff_limit=500)
            large = next(e for e in entries if "add-a-large-file" in e["path"])
            text = (output / large["path"]).read_text(encoding="utf-8")
            self.assertIn("дифф обрезан", text)

    def test_a_session_is_split_by_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transcripts = Path(directory) / "transcripts"
            transcripts.mkdir()
            write_transcript(
                transcripts / "abc12345-0000-0000-0000-000000000000.jsonl",
                [
                    turn("user", "первый вопрос", day="2026-08-19"),
                    turn("assistant", [{"type": "text", "text": "первый ответ"}], day="2026-08-19"),
                    turn("user", "второй вопрос", day="2026-08-20"),
                    turn("assistant", [{"type": "text", "text": "второй ответ"}], day="2026-08-20"),
                ],
            )
            output = Path(directory) / "raw"

            entries = export_conversations(output, transcripts)

            self.assertEqual(
                sorted(entry["path"] for entry in entries),
                ["conversations/2026-08-19-abc12345.md", "conversations/2026-08-20-abc12345.md"],
            )
            first = (output / "conversations/2026-08-19-abc12345.md").read_text(encoding="utf-8")
            self.assertIn("первый вопрос", first)
            self.assertNotIn("второй вопрос", first)

    def test_a_day_with_a_single_turn_is_not_a_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transcripts = Path(directory) / "transcripts"
            transcripts.mkdir()
            write_transcript(
                transcripts / "abc12345-0000-0000-0000-000000000000.jsonl",
                [turn("user", "здравствуйте")],
            )
            self.assertEqual(export_conversations(Path(directory) / "raw", transcripts), [])

    def test_a_missing_transcript_directory_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "nowhere"
            self.assertEqual(export_conversations(Path(directory) / "raw", missing), [])


if __name__ == "__main__":
    unittest.main()

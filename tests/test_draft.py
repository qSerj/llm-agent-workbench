"""Offline tests for the drafting helper. No model is contacted here."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.draft import build_prompt, extract_json, file_tree, reply_text


class ExtractJsonTests(unittest.TestCase):
    """A model answers with prose around the object more often than not."""

    def test_a_bare_object_is_read(self) -> None:
        self.assertEqual(extract_json('{"id": "demo"}'), {"id": "demo"})

    def test_a_fenced_object_is_read(self) -> None:
        text = 'Вот заготовка:\n```json\n{"id": "demo"}\n```\nГотово.'
        self.assertEqual(extract_json(text), {"id": "demo"})

    def test_a_fence_without_a_language_is_read(self) -> None:
        self.assertEqual(extract_json('```\n{"id": "demo"}\n```'), {"id": "demo"})

    def test_prose_around_a_bare_object_is_ignored(self) -> None:
        self.assertEqual(extract_json('Держите: {"id": "demo"} — правьте.'), {"id": "demo"})

    def test_a_reply_without_an_object_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("Не могу помочь.")


class ReplyTextTests(unittest.TestCase):
    def test_only_what_the_model_said_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "opencode.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "step_start", "part": {}}),
                        json.dumps({"type": "text", "part": {"text": "первая"}}),
                        json.dumps({"type": "tool_use", "part": {"text": "не это"}}),
                        "не json",
                        json.dumps({"type": "text", "part": {"text": "вторая"}}),
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(reply_text(path), "первая\nвторая")


class ContextTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.workspace = Path(holder.name)
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
        (self.workspace / "README.md").write_text("проект\n", encoding="utf-8")
        (self.workspace / ".git").mkdir()
        (self.workspace / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    def test_the_tree_lists_real_files_and_skips_dot_directories(self) -> None:
        tree = file_tree(self.workspace)
        self.assertIn("src/main.py", tree)
        self.assertIn("README.md", tree)
        self.assertNotIn(".git", tree)

    def test_a_missing_workspace_does_not_raise(self) -> None:
        self.assertIn("недоступно", file_tree(self.workspace / "absent"))

    def test_the_prompt_carries_the_intent_the_tree_and_the_readme(self) -> None:
        prompt = build_prompt("сравнить два способа", "тесты проходят", self.workspace)
        self.assertIn("сравнить два способа", prompt)
        self.assertIn("тесты проходят", prompt)
        self.assertIn("src/main.py", prompt)
        self.assertIn("проект", prompt)
        self.assertIn("JSON", prompt)

    def test_an_empty_success_criterion_leaves_no_empty_section(self) -> None:
        prompt = build_prompt("сравнить", "   ", self.workspace)
        self.assertNotIn("Что считать хорошим результатом", prompt)


if __name__ == "__main__":
    unittest.main()

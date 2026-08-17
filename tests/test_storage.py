"""Offline tests for recoverable deletion of generated data."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.storage import TRASH_NAME, is_hidden, move_to_trash, unique_name


class TrashTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)

    def make(self, name: str) -> Path:
        target = self.root / name
        (target / "stages").mkdir(parents=True)
        (target / "execution-envelope.json").write_text("{}", encoding="utf-8")
        return target

    def test_deleting_moves_instead_of_destroying(self) -> None:
        target = self.make("run-1")
        moved = move_to_trash(target, self.root)
        self.assertFalse(target.exists())
        self.assertTrue((moved / "execution-envelope.json").is_file())
        self.assertIn(TRASH_NAME, moved.relative_to(self.root).parts)

    def test_a_second_run_of_the_same_name_does_not_overwrite_the_first(self) -> None:
        first = move_to_trash(self.make("run-1"), self.root)
        second = move_to_trash(self.make("run-1"), self.root)
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())

    def test_a_path_outside_the_root_is_refused(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        with self.assertRaises(ValueError):
            move_to_trash(Path(outside.name), self.root)

    def test_the_root_itself_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            move_to_trash(self.root, self.root)

    def test_deleting_twice_is_refused(self) -> None:
        moved = move_to_trash(self.make("run-1"), self.root)
        with self.assertRaises(ValueError):
            move_to_trash(moved, self.root)

    def test_missing_target_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            move_to_trash(self.root / "absent", self.root)


class HiddenTests(unittest.TestCase):
    def test_anything_under_a_dot_directory_is_hidden(self) -> None:
        root = Path("/data")
        self.assertTrue(is_hidden(root / ".trash" / "2026-08-17" / "run", root))
        self.assertTrue(is_hidden(root / ".launch-logs" / "a.log", root))
        self.assertFalse(is_hidden(root / "experiment" / "2026-08-17" / "run", root))

    def test_a_path_outside_the_root_is_not_called_hidden(self) -> None:
        self.assertFalse(is_hidden(Path("/elsewhere/x"), Path("/data")))


class UniqueNameTests(unittest.TestCase):
    def test_a_free_name_is_used_as_is(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(unique_name(Path(raw), "run"), Path(raw) / "run")


if __name__ == "__main__":
    unittest.main()

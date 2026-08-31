"""Чтение локального хранилища оболочки и однозначные ссылки на карточки."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.store import AmbiguousRunReference, Store, decode_reference


def envelope(execution_id: str, started_at: str) -> dict:
    return {
        "execution_id": execution_id,
        "candidate": {"id": "a"},
        "repetition": 1,
        "lifecycle": {"status": "SUCCEEDED", "started_at": started_at},
        "observations": [],
        "stages": [],
        "evaluations": [],
        "artifacts": [],
    }


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.holder = tempfile.TemporaryDirectory()
        self.addCleanup(self.holder.cleanup)
        self.root = Path(self.holder.name)

    def write(self, experiment: str, session: str, started_at: str) -> None:
        directory = self.root / experiment / session / "a-r1"
        directory.mkdir(parents=True)
        document = envelope(f"{experiment}--a--r1", started_at)
        (directory / "execution-envelope.json").write_text(
            json.dumps(document), encoding="utf-8"
        )

    def test_path_key_selects_one_of_duplicate_execution_ids(self) -> None:
        self.write("demo", "2026-08-30", "2026-08-30T10:00:00+00:00")
        self.write("demo", "2026-08-31", "2026-08-31T10:00:00+00:00")
        store = Store(self.root)
        runs = store.runs()
        self.assertEqual(len({run.execution_id for run in runs}), 1)
        self.assertEqual(len({run.key for run in runs}), 2)
        selected = store.run(runs[1].key)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.session, "2026-08-31")
        self.assertEqual(decode_reference(runs[1].key), runs[1].reference)

    def test_ambiguous_legacy_execution_id_is_rejected(self) -> None:
        self.write("demo", "2026-08-30", "2026-08-30T10:00:00+00:00")
        self.write("demo", "2026-08-31", "2026-08-31T10:00:00+00:00")
        with self.assertRaises(AmbiguousRunReference):
            Store(self.root).run("demo--a--r1")

    def test_unique_legacy_execution_id_remains_supported(self) -> None:
        self.write("demo", "2026-08-31", "2026-08-31T10:00:00+00:00")
        run = Store(self.root).run("demo--a--r1")
        self.assertIsNotNone(run)
        self.assertEqual(run.session, "2026-08-31")

    def test_latest_session_is_chosen_for_each_experiment(self) -> None:
        self.write("one", "2026-08-30", "2026-08-30T10:00:00+00:00")
        self.write("one", "2026-08-31", "2026-08-31T10:00:00+00:00")
        self.write("two", "2026-08-29", "2026-08-29T10:00:00+00:00")
        latest = Store(self.root).latest_sessions({"one", "two"})
        self.assertEqual(latest["one"][0].session, "2026-08-31")
        self.assertEqual(latest["two"][0].session, "2026-08-29")


if __name__ == "__main__":
    unittest.main()

"""Offline tests for the evaluation settings the shell shows and saves.

The regression these freeze is real: saving `experiments/wrap-defect` through
the shell used to erase its whole `suite:` block, because the form drew one
evaluation out of five and the description was rebuilt from the form alone.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.evalform import (
    EVALUATOR_FORMS,
    FORM_MARKER,
    evaluate_form_fields,
    evaluate_from_fields,
    form_rows,
    hidden_rows,
    kind_of,
    option_from_text,
    option_text,
    paid_names,
)
from workbench.evaluators import EVALUATORS
from workbench.experiment import (
    dump_experiment,
    leading_comment,
    load_experiment,
    parse_evaluate,
)

try:
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class RegistryTests(unittest.TestCase):
    def test_every_evaluator_has_a_form(self) -> None:
        """The two registries live in different files; a test keeps them in step."""
        self.assertEqual(set(EVALUATOR_FORMS), set(EVALUATORS))

    def test_only_the_judge_spends_money(self) -> None:
        self.assertEqual(paid_names({name: {} for name in EVALUATOR_FORMS}), ["claims"])

    def test_a_summary_says_what_is_not_measured(self) -> None:
        """A person choosing a measurement in a browser is told its limits."""
        for name, form in EVALUATOR_FORMS.items():
            with self.subTest(evaluation=name):
                self.assertTrue(form.summary.strip())
                self.assertGreater(len(form.summary), 60)


class OptionTests(unittest.TestCase):
    def test_a_list_survives_the_single_input(self) -> None:
        text = option_text(["python3", "run_checks.py"])
        self.assertEqual(text, "python3, run_checks.py")
        self.assertEqual(option_from_text("list", text), ["python3", "run_checks.py"])

    def test_a_number_survives(self) -> None:
        self.assertEqual(option_from_text("int", option_text(120)), 120)

    def test_a_number_that_is_not_one_is_passed_on_unrepaired(self) -> None:
        """The evaluator must report the mistake, not the form paper over it."""
        self.assertEqual(option_from_text("int", "вчера"), "вчера")

    def test_blank_means_absent(self) -> None:
        self.assertIsNone(option_from_text("text", "   "))
        self.assertEqual(option_from_text("list", "a,,b"), ["a", "b"])

    def test_kind_is_read_off_a_stored_value(self) -> None:
        self.assertEqual(kind_of(["a"]), "list")
        self.assertEqual(kind_of(600), "int")
        self.assertEqual(kind_of("docs/x.md"), "text")


class FormRowTests(unittest.TestCase):
    def test_stored_keys_come_first_in_their_own_order(self) -> None:
        """dump_experiment writes in insertion order, so the form must not reorder."""
        rows = form_rows("suite", {"timeout": 120, "path": "checks"})
        self.assertEqual([row["option"].name for row in rows][:2], ["timeout", "path"])
        self.assertIn("command", [row["option"].name for row in rows])

    def test_an_unknown_setting_becomes_a_hidden_field_with_its_kind(self) -> None:
        hidden = hidden_rows("suite", {"path": "checks", "env": ["A=1", "B=2"]})
        self.assertEqual(len(hidden), 1)
        self.assertEqual(hidden[0]["name"], "env")
        self.assertEqual(hidden[0]["kind"], "list")


class RoundTripTests(unittest.TestCase):
    def circle(self, evaluate: dict) -> dict:
        return evaluate_from_fields(evaluate_form_fields(evaluate))

    def test_a_suite_block_survives(self) -> None:
        block = {
            "suite": {
                "path": "experiments/wrap-defect/checks",
                "command": ["python3", "run_checks.py"],
                "timeout": 120,
            }
        }
        self.assertEqual(self.circle(block), block)

    def test_several_evaluations_survive_together(self) -> None:
        block = {
            "citations": {"document": "docs/01.md"},
            "mentions": {"document": "docs/01.md"},
            "claims": {"document": "docs/01.md", "model": "test/model"},
        }
        self.assertEqual(self.circle(block), block)

    def test_an_unknown_setting_survives(self) -> None:
        block = {"suite": {"path": "checks", "command": ["python3"], "env": ["A=1"]}}
        self.assertEqual(self.circle(block), block)

    def test_an_unknown_evaluation_survives_and_is_still_refused(self) -> None:
        """Carried through, then rejected by name — never quietly deleted."""
        block = {"whatever": {"document": "docs/01.md"}}
        self.assertEqual(self.circle(block), block)
        with self.assertRaises(ValueError) as caught:
            parse_evaluate(block, "описание")
        self.assertIn("whatever", str(caught.exception))

    def test_clearing_every_checkbox_means_measure_nothing(self) -> None:
        fields = evaluate_form_fields({"citations": {"document": "docs/01.md"}})
        del fields["evaluate.citations.on"]
        self.assertEqual(evaluate_from_fields(fields), {})

    def test_fields_without_the_marker_are_read_as_they_come(self) -> None:
        """A hand-made request, or an old form, still works."""
        self.assertEqual(
            evaluate_from_fields({"evaluate.citations": ["docs/01.md"]}),
            {"citations": {"document": "docs/01.md"}},
        )
        self.assertNotIn(FORM_MARKER, {"evaluate.citations": ["docs/01.md"]})


@unittest.skipUnless(HAS_YAML, "PyYAML is not installed")
class ShippedDescriptionTests(unittest.TestCase):
    """The loss found by hand on 2026-08-18, frozen for every description."""

    def test_every_description_survives_the_form(self) -> None:
        for path in sorted((ROOT / "experiments").glob("*/experiment.yaml")):
            with self.subTest(experiment=path.parent.name):
                experiment = load_experiment(path, root=ROOT)
                circled = evaluate_from_fields(
                    evaluate_form_fields(experiment.evaluate)
                )
                self.assertEqual(circled, experiment.evaluate)

    def test_a_description_edited_and_saved_is_unchanged_on_disk(self) -> None:
        for path in sorted((ROOT / "experiments").glob("*/experiment.yaml")):
            with self.subTest(experiment=path.parent.name):
                original = path.read_text(encoding="utf-8")
                experiment = load_experiment(path, root=ROOT)
                experiment.evaluate = evaluate_from_fields(
                    evaluate_form_fields(experiment.evaluate)
                )
                written = dump_experiment(
                    experiment, root=ROOT, header=leading_comment(original)
                )
                self.assertEqual(original, written)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Свести карточки одного языкового прогона в парную статистику RU/EN."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workbench.analysis import (  # noqa: E402
    Record,
    record_from_envelope,
    summarise_comparison,
)
from workbench.experiment import ComparisonSpec  # noqa: E402


def load_cards(run_directory: Path) -> list[Record]:
    cards: list[Record] = []
    seen: set[tuple[str, int]] = set()
    for path in sorted(run_directory.glob("*/execution-envelope.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        key = (str(envelope["candidate"]["id"]), int(envelope["repetition"]))
        if key in seen:
            raise ValueError(f"повторяющаяся карточка для {key}: {path}")
        seen.add(key)
        cards.append(record_from_envelope(envelope))
    return cards


def format_number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.1f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def print_report(
    cards: list[Record], ru_candidate: str, en_candidate: str
) -> None:
    repetitions = max((card.repetition for card in cards), default=1)
    summary = summarise_comparison(
        cards,
        ComparisonSpec("RU/EN", ru_candidate, en_candidate, "RU", "EN"),
        repetitions,
    )
    pair_count = repetitions - len(
        set(summary.missing_numerator) | set(summary.missing_denominator)
    )
    print(f"Пар найдено: {pair_count}")
    print(f"{'метрика':<22}{'EN среднее':>14}{'RU среднее':>14}{'RU/EN':>12}{'медиана пар':>16}")
    print("-" * 78)
    for metric in summary.metrics:
        if metric.pair_count == 0:
            print(f"{metric.metric.name:<22}{'—':>14}{'—':>14}{'—':>12}{'—':>16}")
            continue
        ratio = "—" if metric.ratio_of_means is None else f"{metric.ratio_of_means:.3f}"
        median = (
            "—" if metric.median_pair_ratio is None else f"{metric.median_pair_ratio:.3f}"
        )
        print(
            f"{metric.metric.name:<22}"
            f"{format_number(metric.denominator_mean):>14}"
            f"{format_number(metric.numerator_mean):>14}"
            f"{ratio:>12}{median:>16}"
        )

    print()
    suite = next((item for item in summary.evaluations if item.name == "suite"), None)
    if suite is None:
        print("suite: —")
        return
    for candidate, outcomes in (
        (en_candidate, suite.denominator),
        (ru_candidate, suite.numerator),
    ):
        passed = outcomes.count("PASS")
        print(f"{candidate}: suite PASS {passed}/{outcomes.total}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path, help="каталог даты с ru-rN и en-rN")
    parser.add_argument("--ru", default="ru", help="ID способа с русской постановкой")
    parser.add_argument("--en", default="en", help="ID способа с английской постановкой")
    arguments = parser.parse_args()
    cards = load_cards(arguments.run_directory)
    if not cards:
        parser.error("в каталоге нет карточек исполнения")
    print_report(cards, arguments.ru, arguments.en)


if __name__ == "__main__":
    main()

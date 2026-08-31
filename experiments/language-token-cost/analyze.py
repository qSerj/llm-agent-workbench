#!/usr/bin/env python3
"""Свести карточки одного языкового прогона в парную статистику RU/EN."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

METRICS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "api_cost",
    "wall_time",
)


def observation(envelope: dict[str, Any], name: str) -> int | float | None:
    for item in envelope.get("observations", []):
        if item.get("name") == name and "stage_id" not in item:
            value = item.get("value")
            return value if isinstance(value, (int, float)) else None
    return None


def load_cards(run_directory: Path) -> dict[tuple[str, int], dict[str, Any]]:
    cards = {}
    for path in sorted(run_directory.glob("*/execution-envelope.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        key = (str(envelope["candidate"]["id"]), int(envelope["repetition"]))
        if key in cards:
            raise ValueError(f"повторяющаяся карточка для {key}: {path}")
        cards[key] = envelope
    return cards


def verdict(envelope: dict[str, Any]) -> str:
    for evaluation in envelope.get("evaluations", []):
        if evaluation.get("id") == "suite":
            return str((evaluation.get("result") or {}).get("verdict") or "—")
    return "—"


def format_number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.1f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def print_report(
    cards: dict[tuple[str, int], dict[str, Any]], ru_candidate: str, en_candidate: str
) -> None:
    repetitions = sorted({repetition for _, repetition in cards})
    pair_count = sum(
        (ru_candidate, repetition) in cards and (en_candidate, repetition) in cards
        for repetition in repetitions
    )
    print(f"Пар найдено: {pair_count}")
    print(f"{'метрика':<22}{'EN среднее':>14}{'RU среднее':>14}{'RU/EN':>12}{'медиана пар':>16}")
    print("-" * 78)
    for metric in METRICS:
        pairs = []
        for repetition in repetitions:
            ru = observation(cards.get((ru_candidate, repetition), {}), metric)
            en = observation(cards.get((en_candidate, repetition), {}), metric)
            if ru is not None and en not in (None, 0):
                pairs.append((float(ru), float(en)))
        if not pairs:
            print(f"{metric:<22}{'—':>14}{'—':>14}{'—':>12}{'—':>16}")
            continue
        ru_mean = statistics.mean(ru for ru, _ in pairs)
        en_mean = statistics.mean(en for _, en in pairs)
        ratio_of_means = ru_mean / en_mean
        median_pair_ratio = statistics.median(ru / en for ru, en in pairs)
        print(
            f"{metric:<22}{format_number(en_mean):>14}{format_number(ru_mean):>14}"
            f"{ratio_of_means:>12.3f}{median_pair_ratio:>16.3f}"
        )

    print()
    for candidate in (en_candidate, ru_candidate):
        outcomes = [
            verdict(envelope)
            for (name, _), envelope in sorted(cards.items())
            if name == candidate
        ]
        passed = sum(item == "PASS" for item in outcomes)
        outcome_text = ", ".join(outcomes) or "—"
        print(f"{candidate}: suite PASS {passed}/{len(outcomes)}; исходы: {outcome_text}")


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

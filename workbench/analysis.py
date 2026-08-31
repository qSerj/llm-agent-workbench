"""Парная статистика по повторяемым исполнениям.

Модуль ничего не знает о языке задачи или веб-оболочке. Описание эксперимента
называет числитель и знаменатель, карточки дают факты, а здесь они соединяются
строго по номеру повтора.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from workbench.experiment import ComparisonSpec


@dataclass(frozen=True)
class MetricSpec:
    name: str
    label: str
    unit: str


METRICS = (
    MetricSpec("input_tokens", "Вход", "tokens"),
    MetricSpec("output_tokens", "Выход", "tokens"),
    MetricSpec("reasoning_tokens", "Рассуждение", "tokens"),
    MetricSpec("cache_read_tokens", "Чтение кэша", "tokens"),
    MetricSpec("cache_write_tokens", "Запись кэша", "tokens"),
    MetricSpec("total_tokens", "Всего токенов", "tokens"),
    MetricSpec("api_cost", "Стоимость", "USD"),
    MetricSpec("wall_time", "Время", "s"),
)


@dataclass(frozen=True)
class Record:
    candidate_id: str
    repetition: int
    status: str
    measurements: dict[str, int | float | None]
    verdicts: dict[str, str]


@dataclass(frozen=True)
class MetricSummary:
    metric: MetricSpec
    pair_count: int
    total_pairs: int
    numerator_mean: float | None
    numerator_median: float | None
    denominator_mean: float | None
    denominator_median: float | None
    ratio_of_means: float | None
    median_pair_ratio: float | None
    ratio_pair_count: int


@dataclass(frozen=True)
class OutcomeCounts:
    total: int
    counts: dict[str, int]
    missing: int

    def count(self, outcome: str) -> int:
        return self.counts.get(outcome, 0)


@dataclass(frozen=True)
class PairedOutcomes:
    name: str
    numerator: OutcomeCounts
    denominator: OutcomeCounts


@dataclass(frozen=True)
class ComparisonSummary:
    comparison: ComparisonSpec
    metrics: tuple[MetricSummary, ...]
    lifecycle: PairedOutcomes
    evaluations: tuple[PairedOutcomes, ...]
    repetitions: tuple[int, ...]
    missing_numerator: tuple[int, ...]
    missing_denominator: tuple[int, ...]

    def metric(self, name: str) -> MetricSummary:
        for item in self.metrics:
            if item.metric.name == name:
                return item
        raise KeyError(name)


def numeric(value: Any) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def record_from_envelope(envelope: dict[str, Any]) -> Record:
    measurements: dict[str, int | float | None] = {}
    for item in envelope.get("observations", []):
        if "stage_id" not in item:
            measurements[str(item.get("name"))] = numeric(item.get("value"))

    verdicts: dict[str, str] = {}
    for evaluation in envelope.get("evaluations", []):
        result = evaluation.get("result") or {}
        verdict = result.get("verdict")
        if verdict:
            verdicts[str(evaluation.get("id"))] = str(verdict)
    return Record(
        candidate_id=str(envelope["candidate"]["id"]),
        repetition=int(envelope["repetition"]),
        status=str(envelope["lifecycle"]["status"]),
        measurements=measurements,
        verdicts=verdicts,
    )


def indexed_records(records: list[Record]) -> dict[tuple[str, int], Record]:
    indexed: dict[tuple[str, int], Record] = {}
    for record in records:
        key = (record.candidate_id, record.repetition)
        if key in indexed:
            raise ValueError(f"duplicate execution for {record.candidate_id} r{record.repetition}")
        indexed[key] = record
    return indexed


def outcome_counts(values: list[str | None]) -> OutcomeCounts:
    counts: dict[str, int] = {}
    for value in values:
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    return OutcomeCounts(total=len(values), counts=counts, missing=values.count(None))


def metric_summary(
    metric: MetricSpec,
    pairs: list[tuple[Record | None, Record | None]],
) -> MetricSummary:
    complete: list[tuple[float, float]] = []
    for numerator, denominator in pairs:
        if numerator is None or denominator is None:
            continue
        numerator_value = numeric(numerator.measurements.get(metric.name))
        denominator_value = numeric(denominator.measurements.get(metric.name))
        if numerator_value is not None and denominator_value is not None:
            complete.append((float(numerator_value), float(denominator_value)))

    if not complete:
        return MetricSummary(metric, 0, len(pairs), None, None, None, None, None, None, 0)

    numerator_values = [item[0] for item in complete]
    denominator_values = [item[1] for item in complete]
    numerator_mean = statistics.mean(numerator_values)
    denominator_mean = statistics.mean(denominator_values)
    ratios = [numerator / denominator for numerator, denominator in complete if denominator]
    return MetricSummary(
        metric=metric,
        pair_count=len(complete),
        total_pairs=len(pairs),
        numerator_mean=numerator_mean,
        numerator_median=statistics.median(numerator_values),
        denominator_mean=denominator_mean,
        denominator_median=statistics.median(denominator_values),
        ratio_of_means=(numerator_mean / denominator_mean if denominator_mean else None),
        median_pair_ratio=statistics.median(ratios) if ratios else None,
        ratio_pair_count=len(ratios),
    )


def paired_outcomes(
    name: str,
    pairs: list[tuple[Record | None, Record | None]],
    value: Callable[[Record], str | None],
) -> PairedOutcomes:
    return PairedOutcomes(
        name=name,
        numerator=outcome_counts(
            [value(numerator) if numerator is not None else None for numerator, _ in pairs]
        ),
        denominator=outcome_counts(
            [value(denominator) if denominator is not None else None for _, denominator in pairs]
        ),
    )


def summarise_comparison(
    records: list[Record], comparison: ComparisonSpec, repetitions: int
) -> ComparisonSummary:
    indexed = indexed_records(records)
    actual = {
        repetition
        for candidate, repetition in indexed
        if candidate in {comparison.numerator, comparison.denominator}
    }
    repetition_numbers = tuple(sorted(set(range(1, repetitions + 1)) | actual))
    pairs = [
        (
            indexed.get((comparison.numerator, repetition)),
            indexed.get((comparison.denominator, repetition)),
        )
        for repetition in repetition_numbers
    ]
    evaluations = sorted(
        {
            name
            for pair in pairs
            for record in pair
            if record is not None
            for name in record.verdicts
        }
    )
    return ComparisonSummary(
        comparison=comparison,
        metrics=tuple(metric_summary(metric, pairs) for metric in METRICS),
        lifecycle=paired_outcomes("lifecycle", pairs, lambda record: record.status),
        evaluations=tuple(
            paired_outcomes(name, pairs, lambda record, key=name: record.verdicts.get(key))
            for name in evaluations
        ),
        repetitions=repetition_numbers,
        missing_numerator=tuple(
            repetition
            for repetition, (numerator, _) in zip(repetition_numbers, pairs, strict=True)
            if numerator is None
        ),
        missing_denominator=tuple(
            repetition
            for repetition, (_, denominator) in zip(repetition_numbers, pairs, strict=True)
            if denominator is None
        ),
    )

#!/usr/bin/env python3
"""Скрытые проверки договора collapse_ranges."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable


def check_value(ranges: object, values: object, expected: str) -> tuple[bool, str]:
    actual = ranges.collapse_ranges(values)
    return actual == expected, f"ожидалось {expected!r}, получено {actual!r}"


def check_empty(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [], "")


def check_single(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [7], "7")


def check_pair_is_not_collapsed(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [8, 7], "7,8")


def check_long_run_is_collapsed(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [3, 1, 2], "1-3")


def check_mixed_runs(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [11, 1, 3, 2, 7, 8, 10], "1-3,7,8,10,11")


def check_duplicates(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [3, 2, 2, 1, 3, 3], "1-3")


def check_negative_range(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, [-1, -3, -2, 2], "-3--1,2")


def check_iterator(ranges: object) -> tuple[bool, str]:
    return check_value(ranges, iter([6, 4, 5]), "4-6")


def check_input_is_not_mutated(ranges: object) -> tuple[bool, str]:
    values = [3, 1, 2]
    ranges.collapse_ranges(values)
    return values == [3, 1, 2], f"вход изменён: {values!r}"


def check_invalid_values(ranges: object) -> tuple[bool, str]:
    for value in (True, 1.5, "2", None):
        try:
            ranges.collapse_ranges([1, value, 3])
        except TypeError:
            continue
        except Exception as error:
            return False, f"для {value!r} поднят {type(error).__name__}, а не TypeError"
        return False, f"недопустимое значение {value!r} было принято"
    return True, "bool и нецелые значения отклонены через TypeError"


CHECKS: list[tuple[str, Callable[[object], tuple[bool, str]]]] = [
    ("empty", check_empty),
    ("single", check_single),
    ("pair-is-not-collapsed", check_pair_is_not_collapsed),
    ("long-run-is-collapsed", check_long_run_is_collapsed),
    ("mixed-runs", check_mixed_runs),
    ("duplicates", check_duplicates),
    ("negative-range", check_negative_range),
    ("iterator", check_iterator),
    ("input-is-not-mutated", check_input_is_not_mutated),
    ("invalid-values", check_invalid_values),
]


def main() -> None:
    try:
        import ranges
    except Exception as error:
        print(
            json.dumps(
                {
                    "checks": [
                        {
                            "id": name,
                            "outcome": "UNDETERMINED",
                            "rationale": f"ranges.py не импортируется: {error}",
                        }
                        for name, _ in CHECKS
                    ]
                },
                ensure_ascii=False,
            )
        )
        return

    checks = []
    for name, check in CHECKS:
        try:
            ok, rationale = check(ranges)
            outcome = "PASS" if ok else "FAIL"
        except Exception as error:
            outcome = "FAIL"
            rationale = f"{type(error).__name__}: {error}"
        checks.append({"id": name, "outcome": outcome, "rationale": rationale})
    print(json.dumps({"checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())

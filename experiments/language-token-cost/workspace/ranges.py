"""Compact integer sequences for display."""

from __future__ import annotations

from collections.abc import Iterable


def collapse_ranges(values: Iterable[int]) -> str:
    """Return a comma-separated compact representation of integer values."""
    ordered = sorted(values)
    if not ordered:
        return ""

    fragments: list[str] = []
    start = ordered[0]
    end = start
    for value in ordered[1:]:
        if value <= end + 1:
            end = value
            continue
        fragments.append(_format_run(start, end))
        start = end = value
    fragments.append(_format_run(start, end))
    return ",".join(fragments)


def _format_run(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}-{end}"

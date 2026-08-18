"""Show what actually differs between two candidates, or between two results.

Two chains that differ by one line in one prompt look identical in a table and
identical side by side. The difference is the whole point of the experiment, so
it is worth computing rather than leaving to the reader's memory.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

CONTEXT_LINES = 3


@dataclass
class Line:
    """One rendered line of a unified diff, tagged by what happened to it."""

    kind: str  # meta | added | removed | context
    text: str


def diff_lines(
    before: str, after: str, before_label: str, after_label: str
) -> list[Line]:
    """A unified diff, already classified for display."""
    rows: list[Line] = []
    for raw in difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=before_label,
        tofile=after_label,
        lineterm="",
        n=CONTEXT_LINES,
    ):
        if raw.startswith(("---", "+++", "@@")):
            rows.append(Line("meta", raw))
        elif raw.startswith("+"):
            rows.append(Line("added", raw[1:]))
        elif raw.startswith("-"):
            rows.append(Line("removed", raw[1:]))
        else:
            rows.append(Line("context", raw[1:] if raw.startswith(" ") else raw))
    return rows


def stage_field(stage: Any, name: str) -> str:
    """Read one field off a stage of a description, whatever shape it has."""
    value = stage.get(name) if isinstance(stage, dict) else getattr(stage, name, None)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return "" if value is None else str(value)


STAGE_FIELDS = ("role", "model", "prompt", "allow_edit", "allow_bash")


def stage_rows(
    left: list[Any], right: list[Any], fields: tuple[str, ...] = STAGE_FIELDS
) -> list[dict[str, Any]]:
    """Line up two chains stage by stage and say where they part.

    Chains of different length are compared by position, with the missing side
    left blank: a chain that has an extra stage differs by exactly that stage.
    """
    rows: list[dict[str, Any]] = []
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        for name in fields:
            before = stage_field(a, name) if a is not None else ""
            after = stage_field(b, name) if b is not None else ""
            rows.append(
                {
                    "stage": index + 1,
                    "field": name,
                    "before": before,
                    "after": after,
                    "same": before == after,
                }
            )
    return rows


def differing_prompts(
    left: list[Any], right: list[Any], read: Any
) -> list[tuple[str, str, list[Line]]]:
    """Diff the prompt files two chains use, skipping the ones they share.

    ``read`` turns a prompt reference into text; a prompt that cannot be read is
    reported as empty rather than raising, because a broken reference is exactly
    what the reader is looking for.
    """
    pairs: list[tuple[str, str, list[Line]]] = []
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        before_name = stage_field(a, "prompt") if a is not None else ""
        after_name = stage_field(b, "prompt") if b is not None else ""
        if before_name == after_name:
            continue
        absent = "(нет этапа)"
        rows = diff_lines(
            read(before_name),
            read(after_name),
            before_name or absent,
            after_name or absent,
        )
        pairs.append((before_name, after_name, rows))
    return pairs

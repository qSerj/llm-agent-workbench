"""Move generated data out of sight without destroying it.

A run costs money and cannot be reproduced exactly — models are not
deterministic — so the shell never unlinks one. Deleting moves the directory
into a trash folder beside it, where it stops being listed but stays on disk
until a human removes it.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

TRASH_NAME = ".trash"


def is_hidden(path: Path, root: Path) -> bool:
    """True for anything under a dot-directory, trash and launch logs included."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return any(part.startswith(".") for part in parts)


def unique_name(directory: Path, name: str) -> Path:
    """A free path inside ``directory``, suffixed only if the name is taken."""
    candidate = directory / name
    attempt = 2
    while candidate.exists():
        candidate = directory / f"{name}-{attempt}"
        attempt += 1
    return candidate


def move_to_trash(target: Path, root: Path) -> Path:
    """Move ``target`` into ``root/.trash/<day>/``, and say where it went.

    Refuses anything that is not a directory inside ``root``, and anything
    already in the trash: the point is to make deletion recoverable, not to
    offer a second way to lose data.
    """
    target = target.resolve()
    root = root.resolve()
    if not target.is_dir():
        raise ValueError(f"нечего удалять: {target}")
    if not target.is_relative_to(root) or target == root:
        raise ValueError(f"вне каталога {root}: {target}")
    if TRASH_NAME in target.relative_to(root).parts:
        raise ValueError(f"уже в корзине: {target}")

    day = datetime.now(UTC).date().isoformat()
    destination = root / TRASH_NAME / day
    destination.mkdir(parents=True, exist_ok=True)
    moved = unique_name(destination, target.name)
    shutil.move(str(target), str(moved))
    return moved

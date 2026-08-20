#!/usr/bin/env python3
"""Export this repository's own history as raw sources for an llm-wiki.

    .research-env/bin/python3 tools/export_history.py --output ~/wiki/agentsworkbench/raw

Re-running it is how sources are refreshed: file names are stable, so a source
that did not change keeps its digest and a ledger-keeping schema skips it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.history import (
    DEFAULT_DIFF_LIMIT,
    export_commits,
    export_conversations,
    export_documents,
    write_manifest,
)

TRANSCRIPT_ROOT = Path.home() / ".claude" / "projects"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="каталог raw/ для вики")
    parser.add_argument(
        "--diff-limit",
        type=int,
        default=DEFAULT_DIFF_LIMIT,
        help=f"обрезать дифф коммита после N байт (по умолчанию {DEFAULT_DIFF_LIMIT})",
    )
    parser.add_argument(
        "--transcripts",
        type=Path,
        default=TRANSCRIPT_ROOT / str(ROOT).replace("/", "-"),
        help="каталог со стенограммами разговоров",
    )
    parser.add_argument(
        "--skip",
        choices=("documents", "commits", "conversations"),
        action="append",
        default=[],
        help="не выгружать этот вид источников",
    )
    arguments = parser.parse_args()

    output = arguments.output.expanduser().resolve()
    entries: list[dict[str, Any]] = []
    if "documents" not in arguments.skip:
        entries += export_documents(ROOT, output)
    if "commits" not in arguments.skip:
        entries += export_commits(ROOT, output, arguments.diff_limit)
    if "conversations" not in arguments.skip:
        entries += export_conversations(output, arguments.transcripts.expanduser())

    manifest = write_manifest(ROOT, output, entries)

    by_kind: dict[str, int] = {}
    for entry in entries:
        by_kind[entry["kind"]] = by_kind.get(entry["kind"], 0) + 1
    print(f"выгружено в {output}")
    for kind, count in sorted(by_kind.items()):
        print(f"  {kind}: {count}")
    print(f"  всего {len(entries)} источников, {sum(e['bytes'] for e in entries) // 1024} КБ")
    print(f"  реестр: {manifest.relative_to(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

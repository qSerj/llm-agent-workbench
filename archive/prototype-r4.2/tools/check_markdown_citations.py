#!/usr/bin/env python3
"""Проверить существование локальных ссылок вида `путь:строка` в Markdown."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CITATION = re.compile(r"`(?P<path>(?:src|docs)/[^`:\n]+):(?P<line>[1-9][0-9]*)`")


def check_citations(document: Path, root: Path) -> dict:
    checks = []
    for match in CITATION.finditer(document.read_text(encoding="utf-8")):
        relative = match.group("path")
        line = int(match.group("line"))
        target = (root / relative).resolve()
        valid_path = target.is_relative_to(root.resolve()) and target.is_file()
        line_count = None
        if valid_path:
            line_count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        ok = bool(valid_path and line_count is not None and line <= line_count)
        checks.append(
            {
                "citation": f"{relative}:{line}",
                "ok": ok,
                "line_count": line_count,
                "reason": "valid" if ok else "missing file or line outside file",
            }
        )
    return {
        "verdict": "PASS" if checks and all(item["ok"] for item in checks) else "FAIL",
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = check_citations(args.document, args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()

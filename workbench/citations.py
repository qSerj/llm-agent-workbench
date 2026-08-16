"""Check that `path:line` citations in Markdown point at lines that exist.

This is the cheap deterministic check that caught a real regression: a chain
rewrote a correct citation `ProfileUsageExample.cs:5` into `:11` in a file that
has ten lines, while the grader still returned a perfect score. Run it before
any model-based review — existence of a line is verified more reliably and far
more cheaply by a program.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

CITATION = re.compile(r"`(?P<path>(?:src|docs)/[^`:\n]+):(?P<line>[1-9][0-9]*)`")
POLICY = {"id": "markdown-line-citations", "version": "1"}


def check_citations(document: Path, root: Path) -> dict[str, Any]:
    """Return a verdict plus one check per citation found in ``document``."""
    root = root.resolve()
    checks: list[dict[str, Any]] = []
    for match in CITATION.finditer(document.read_text(encoding="utf-8")):
        relative = match.group("path")
        line = int(match.group("line"))
        target = (root / relative).resolve()
        readable = target.is_relative_to(root) and target.is_file()
        line_count = None
        if readable:
            text = target.read_text(encoding="utf-8", errors="replace")
            line_count = len(text.splitlines())
        ok = bool(readable and line_count is not None and line <= line_count)
        if ok:
            rationale = "line exists"
        elif not readable:
            rationale = "cited file is missing or outside the workspace"
        else:
            rationale = f"line {line} is past the end of the file ({line_count} lines)"
        checks.append(
            {
                "id": f"{relative}:{line}",
                "outcome": "PASS" if ok else "FAIL",
                "value": line_count,
                "rationale": rationale,
            }
        )

    if not checks:
        # No citation is not the same as a broken one, and not the same as a
        # sound one. The document simply offers nothing to verify here.
        verdict = "UNDETERMINED"
    elif all(item["outcome"] == "PASS" for item in checks):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"verdict": verdict, "checks": checks}


def citation_evaluation(
    evaluation_id: str,
    document: Path,
    root: Path,
    subject_artifact_id: str,
    evidence_artifact_ids: list[str],
) -> dict[str, Any]:
    """Express the citation check as a ``CODE`` evaluation for an envelope."""
    result = check_citations(document, root)
    broken = [item["id"] for item in result["checks"] if item["outcome"] == "FAIL"]
    if result["verdict"] == "UNDETERMINED":
        rationale = "The document contains no `path:line` citations to verify."
    elif broken:
        rationale = "Citations pointing at missing lines: " + ", ".join(broken)
    else:
        rationale = f"All {len(result['checks'])} citations resolve to existing lines."

    return {
        "id": evaluation_id,
        "subject": {"kind": "ARTIFACT", "id": subject_artifact_id},
        "evaluator": {"source": "CODE", "identity": "workbench.citations"},
        "policy": dict(POLICY),
        "result": result,
        "rationale": rationale,
        "evidence_artifact_ids": evidence_artifact_ids,
    }

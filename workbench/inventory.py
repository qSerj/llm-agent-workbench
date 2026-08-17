"""Derive, from the sources themselves, what a document about them must cover.

The point of deriving rather than listing: a hand-written checklist saturates.
The archived benchmark scored every candidate 16/16 on one and so separated
nothing. An inventory read out of the material grows with the material and
cannot be quietly satisfied in advance.

Extraction is deliberately shallow — declarations, not semantics — and the
language must be named by the experiment. A shallow reading that says what it
covers is honest; a clever one that silently misses a construct is not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# `public sealed class Foo`, `public interface IFoo`, `public record Bar`.
CSHARP_TYPE = re.compile(
    r"^\s*public\s+(?:[a-z]+\s+)*(?:class|interface|struct|record|enum)\s+"
    r"(?P<name>[A-Za-z_]\w*)",
    re.MULTILINE,
)
# `public int BranchCount { get; }`, `public const int MaxBranches = 16;`,
# `public IReadOnlyList<int> ToRegisters()`, `public string Kind => "simple";`
CSHARP_MEMBER = re.compile(
    r"^\s*public\s+(?:[a-z]+\s+)*[\w<>,\[\]?.]+\s+(?P<name>[A-Za-z_]\w*)\s*[({=;]",
    re.MULTILINE,
)

LANGUAGES: dict[str, dict[str, Any]] = {
    "csharp": {
        "glob": "**/*.cs",
        "patterns": (CSHARP_TYPE, CSHARP_MEMBER),
        "covers": "публичные типы и члены, объявленные словом public",
    },
}

POLICY = {"id": "public-api-coverage", "version": "1"}


def public_names(workspace: Path, language: str) -> list[str]:
    """Every public name the sources declare, sorted and without repeats.

    A name declared in several places collapses to one entry: coverage is asked
    of the document, and the document mentions a name, not a declaration.
    """
    if language not in LANGUAGES:
        known = ", ".join(sorted(LANGUAGES))
        raise ValueError(f"неизвестный язык для перечня: {language}; известны: {known}")
    rules = LANGUAGES[language]
    found: set[str] = set()
    for path in sorted(workspace.glob(str(rules["glob"]))):
        if any(part in {"obj", "bin"} or part.startswith(".") for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in rules["patterns"]:
            for match in pattern.finditer(text):
                found.add(match.group("name"))
    return sorted(found)


def check_coverage(document: Path, workspace: Path, language: str) -> dict[str, Any]:
    """Return a verdict plus one check per public name the sources declare."""
    names = public_names(workspace, language)
    text = document.read_text(encoding="utf-8", errors="replace")
    checks = [
        {
            "id": name,
            "outcome": "PASS" if name in text else "FAIL",
            "value": text.count(name),
            "rationale": (
                "упомянуто в документе" if name in text else "в документе не встречается"
            ),
        }
        for name in names
    ]

    if not checks:
        # Nothing was extracted: either the workspace holds no sources of this
        # language, or the extractor does not understand them. Either way the
        # document has not been shown to be incomplete.
        verdict = "UNDETERMINED"
    elif all(item["outcome"] == "PASS" for item in checks):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"verdict": verdict, "checks": checks}


def coverage_evaluation(
    evaluation_id: str,
    document: Path,
    workspace: Path,
    language: str,
    subject_artifact_id: str,
    evidence_artifact_ids: list[str],
) -> dict[str, Any]:
    """Wrap the coverage result as an envelope evaluation."""
    result = check_coverage(document, workspace, language)
    missing = [item["id"] for item in result["checks"] if item["outcome"] == "FAIL"]
    total = len(result["checks"])
    if not total:
        rationale = f"нечего сверять: перечень публичных имён ({language}) пуст"
    elif missing:
        shown = ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
        rationale = f"не упомянуто {len(missing)} из {total}: {shown}"
    else:
        rationale = f"все {total} публичных имён упомянуты"
    return {
        "id": evaluation_id,
        "subject": {"kind": "ARTIFACT", "id": subject_artifact_id},
        "evaluator": {"source": "CODE", "identity": "workbench.inventory"},
        "policy": dict(POLICY),
        "result": result,
        "rationale": rationale,
        "evidence_artifact_ids": list(evidence_artifact_ids),
    }

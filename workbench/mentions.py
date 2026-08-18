"""Check that every code name a document mentions exists in the sources.

``workbench.inventory`` reads from the sources towards the document and answers
completeness: is every public name mentioned? This reads the other way and
answers invention: does every mentioned name exist? The two are not the same
question, and neither implies the other.

Invention was the failure a human caught on 2026-08-13 while a sixteen-point
checklist returned 16/16: the document showed a usage example built out of an
API that was not there. Prose invention stays out of reach of a program — that
needs a judge — but an invented *name* does not. It is caught deterministically
and for free.

The reading is deliberately shallow, and what it covers is stated rather than
implied:

* only what the document marks as code is read — inline spans and fenced
  blocks. Prose is not scanned, so a name written as ordinary text is missed;
* only names carrying an upper-case letter are taken as claims about the code,
  which is what a C# type, member or camel-case parameter looks like. A word
  written entirely in lower case — ``int``, ``delays`` — is skipped on purpose
  rather than guessed at;
* a name counts as existing if it occurs anywhere in the sources — in a
  declaration, a call or a comment. The question here is invention, not
  visibility, and a stricter rule would report private names as invented;
* consequently a name from the platform's own library that the sources never
  use is reported as unfounded. That is a blunt answer to a real observation:
  the document is talking about something this material does not contain.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

CODE_SPAN = re.compile(r"`([^`\n]+)`")
FENCED_BLOCK = re.compile(r"^```[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
TOKEN = re.compile(r"[A-Za-z_]\w*")
UPPER = re.compile(r"[A-Z]")

LANGUAGES: dict[str, dict[str, Any]] = {
    "csharp": {
        "glob": "**/*.cs",
        # Words that look like names but say nothing about this repository.
        "skip": frozenset(
            {
                "TODO",
                "NOTE",
                "JSON",
                "XML",
                "HTTP",
                "API",
                "README",
                "GET",
                "POST",
            }
        ),
        "covers": "имена с заглавной буквой внутри кодовых вставок документа",
    },
}

POLICY = {"id": "mentioned-identifiers-exist", "version": "1"}


def code_fragments(text: str) -> list[str]:
    """Everything the document itself marked as code."""
    return CODE_SPAN.findall(text) + FENCED_BLOCK.findall(text)


def mentioned_names(document: Path, language: str) -> list[str]:
    """Names the document states as code, sorted and without repeats."""
    rules = language_rules(language)
    skip = rules["skip"]
    found: set[str] = set()
    text = document.read_text(encoding="utf-8", errors="replace")
    for fragment in code_fragments(text):
        if "/" in fragment:
            # A path is a citation, and citations are checked by their own
            # evaluator against the line they point at.
            continue
        for match in TOKEN.finditer(fragment):
            name = match.group(0)
            if len(name) >= 3 and UPPER.search(name) and name not in skip:
                found.add(name)
    return sorted(found)


def language_rules(language: str) -> dict[str, Any]:
    if language not in LANGUAGES:
        known = ", ".join(sorted(LANGUAGES))
        raise ValueError(f"неизвестный язык для проверки имён: {language}; известны: {known}")
    return LANGUAGES[language]


def source_text(workspace: Path, language: str) -> str:
    """Every source file of the language, read once and joined."""
    rules = language_rules(language)
    parts: list[str] = []
    for path in sorted(workspace.glob(str(rules["glob"]))):
        if any(part in {"obj", "bin"} or part.startswith(".") for part in path.parts):
            continue
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def check_mentions(document: Path, workspace: Path, language: str) -> dict[str, Any]:
    """Return a verdict plus one check per name the document states as code."""
    names = mentioned_names(document, language)
    sources = source_text(workspace, language)
    checks: list[dict[str, Any]] = []
    for name in names:
        occurrences = len(re.findall(rf"\b{re.escape(name)}\b", sources))
        checks.append(
            {
                "id": name,
                "outcome": "PASS" if occurrences else "FAIL",
                "value": occurrences,
                "rationale": (
                    f"встречается в исходниках {occurrences} раз"
                    if occurrences
                    else "в исходниках не встречается ни разу"
                ),
            }
        )

    if not sources:
        # Nothing to check against. Silence about the sources is not a clean
        # bill for the document (ADR 0004).
        verdict = "UNDETERMINED"
    elif not checks:
        # The document names no code at all: nothing here to be invented.
        verdict = "UNDETERMINED"
    elif all(item["outcome"] == "PASS" for item in checks):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"verdict": verdict, "checks": checks}


def mentions_evaluation(
    evaluation_id: str,
    document: Path,
    workspace: Path,
    language: str,
    subject_artifact_id: str,
    evidence_artifact_ids: list[str],
) -> dict[str, Any]:
    """Wrap the invention check as a ``CODE`` evaluation for an envelope."""
    result = check_mentions(document, workspace, language)
    invented = [item["id"] for item in result["checks"] if item["outcome"] == "FAIL"]
    total = len(result["checks"])
    if result["verdict"] == "UNDETERMINED" and not total:
        rationale = "документ не называет ни одного имени кода"
    elif result["verdict"] == "UNDETERMINED":
        rationale = f"нечего сверять: исходников ({language}) не найдено"
    elif invented:
        shown = ", ".join(invented[:8]) + ("…" if len(invented) > 8 else "")
        rationale = f"нет в исходниках {len(invented)} из {total}: {shown}"
    else:
        rationale = f"все упомянутые имена есть в исходниках ({total})"
    return {
        "id": evaluation_id,
        "subject": {"kind": "ARTIFACT", "id": subject_artifact_id},
        "evaluator": {"source": "CODE", "identity": "workbench.mentions"},
        "policy": dict(POLICY),
        "result": result,
        "rationale": rationale,
        "evidence_artifact_ids": list(evidence_artifact_ids),
    }

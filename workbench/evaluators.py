"""The named evaluations an experiment can ask for, and how they are attached.

``evaluate:`` in a description is a registry: a name picks an evaluator, and the
value configures it. Until now the shape was a registry but the behaviour was one
hard-coded branch, and any other name was parsed, stored and silently dropped.
Silence is the wrong answer to a name nobody implements — an experiment that asks
for a measurement it will not get should say so before it spends money.

Evaluations accumulate. A run is finished when its stages are; its evaluations
may arrive later, from a program, a model or a person, which is why they are an
array and why ``tools/evaluate_run.py`` may add to a stored envelope.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workbench.citations import citation_evaluation
from workbench.envelope import directory_artifact, file_artifact
from workbench.inventory import coverage_evaluation
from workbench.judge import claims_evaluation, judge_document
from workbench.mentions import mentions_evaluation
from workbench.suite import (
    SUITE_MEDIA_TYPE,
    check_suite_options,
    run_suite,
    suite_command,
    suite_evaluation,
    suite_path,
    suite_timeout,
)

DOCUMENT_ARTIFACT = "final-document"
SUITE_ARTIFACT = "check-suite"
SUITE_LOG_ARTIFACT = "check-suite-output"

# The project is not installable: descriptions name their workspace and their
# check suite relative to the repository root, and tools are run from it.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def final_workspace_artifact(envelope: dict[str, Any]) -> str | None:
    """The artifact the last stage left behind — the run's result as a whole."""
    stages = envelope.get("stages") or []
    if not stages or not stages[-1]["output_artifact_ids"]:
        return None
    return stages[-1]["output_artifact_ids"][0]


def final_workspace(envelope: dict[str, Any], bundle_root: Path) -> Path | None:
    """Locate the workspace the last stage left behind, via the envelope itself."""
    artifact_id = final_workspace_artifact(envelope)
    if artifact_id is None:
        return None
    for artifact in envelope["artifacts"]:
        if artifact["id"] == artifact_id and "path" in artifact["location"]:
            return bundle_root / artifact["location"]["path"]
    return None


def options_for(raw: Any) -> dict[str, Any]:
    """A plain string is shorthand for the document; a mapping is the long form."""
    if isinstance(raw, str):
        return {"document": raw}
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    raise ValueError("настройки оценки должны быть строкой или отображением")


def ensure_document(
    envelope: dict[str, Any], bundle_root: Path, options: dict[str, Any]
) -> tuple[Path, Path] | None:
    """Record the produced document once, however many evaluations want it."""
    relative = str(options.get("document") or "")
    if not relative:
        raise ValueError("оценке нужен путь document")
    workspace = final_workspace(envelope, bundle_root)
    if workspace is None:
        return None
    document = workspace / relative
    if not document.is_file():
        print(f"  документ не создан: {relative}")
        return None
    known = {artifact["id"] for artifact in envelope["artifacts"]}
    if DOCUMENT_ARTIFACT not in known:
        envelope["artifacts"].append(
            file_artifact(
                DOCUMENT_ARTIFACT, "OUTPUT", document, bundle_root, "text/markdown"
            )
        )
    return workspace, document


def replace_evaluation(envelope: dict[str, Any], evaluation: dict[str, Any]) -> None:
    """Keep one evaluation per name: re-judging replaces, it does not accumulate."""
    envelope["evaluations"] = [
        item for item in envelope["evaluations"] if item["id"] != evaluation["id"]
    ]
    envelope["evaluations"].append(evaluation)


def attach_citations(
    envelope: dict[str, Any], bundle_root: Path, options: dict[str, Any]
) -> None:
    found = ensure_document(envelope, bundle_root, options)
    if found is None:
        return
    workspace, document = found
    replace_evaluation(
        envelope,
        citation_evaluation(
            evaluation_id="citations",
            document=document,
            root=workspace,
            subject_artifact_id=DOCUMENT_ARTIFACT,
            evidence_artifact_ids=[DOCUMENT_ARTIFACT],
        ),
    )


def attach_completeness(
    envelope: dict[str, Any], bundle_root: Path, options: dict[str, Any]
) -> None:
    found = ensure_document(envelope, bundle_root, options)
    if found is None:
        return
    workspace, document = found
    replace_evaluation(
        envelope,
        coverage_evaluation(
            evaluation_id="completeness",
            document=document,
            workspace=workspace,
            language=str(options.get("language") or "csharp"),
            subject_artifact_id=DOCUMENT_ARTIFACT,
            evidence_artifact_ids=[DOCUMENT_ARTIFACT],
        ),
    )


def attach_mentions(
    envelope: dict[str, Any], bundle_root: Path, options: dict[str, Any]
) -> None:
    found = ensure_document(envelope, bundle_root, options)
    if found is None:
        return
    workspace, document = found
    replace_evaluation(
        envelope,
        mentions_evaluation(
            evaluation_id="mentions",
            document=document,
            workspace=workspace,
            language=str(options.get("language") or "csharp"),
            subject_artifact_id=DOCUMENT_ARTIFACT,
            evidence_artifact_ids=[DOCUMENT_ARTIFACT],
        ),
    )


def attach_claims(
    envelope: dict[str, Any], bundle_root: Path, options: dict[str, Any]
) -> None:
    found = ensure_document(envelope, bundle_root, options)
    if found is None:
        return
    workspace, _ = found
    model = str(options.get("model") or "")
    if not model:
        raise ValueError("оценке claims нужна модель-судья: evaluate.claims.model")
    provider = str(options.get("provider") or "openrouter")
    ruling = judge_document(
        workspace=workspace,
        document_relative=str(options["document"]),
        model=model,
        provider=provider,
        base_url=options.get("base_url"),
    )
    replace_evaluation(
        envelope,
        claims_evaluation(
            evaluation_id="claims",
            ruling=ruling,
            provider=provider,
            subject_artifact_id=DOCUMENT_ARTIFACT,
            evidence_artifact_ids=[DOCUMENT_ARTIFACT],
        ),
    )
    # What judging cost is not what solving cost. Kept apart by name so that a
    # comparison of candidates never quietly includes the price of measuring.
    envelope["observations"] = [
        item for item in envelope["observations"] if item["name"] != "judge_cost"
    ]
    envelope["observations"].append(
        {
            "name": "judge_cost",
            "value": ruling["api_cost_usd"],
            "unit": "usd",
            "method": f"opencode/{ruling['model']}",
        }
    )


def attach_suite(
    envelope: dict[str, Any], bundle_root: Path, options: dict[str, Any]
) -> None:
    """Measure the finished workspace against checks it never contained."""
    workspace = final_workspace(envelope, bundle_root)
    subject = final_workspace_artifact(envelope)
    if workspace is None or subject is None:
        return
    suite = suite_path(options, REPOSITORY_ROOT)
    if not suite.is_dir():
        raise ValueError(f"каталог проверок не найден: {suite}")

    command = suite_command(options)
    result = run_suite(
        workspace=workspace,
        suite=suite,
        command=command,
        timeout=suite_timeout(options),
    )

    # The card must say which version of the reference it was measured against,
    # so the suite travels with the run and is checksummed like everything else.
    stored = bundle_root / SUITE_ARTIFACT
    if stored.exists():
        shutil.rmtree(stored)
    shutil.copytree(suite, stored, ignore=shutil.ignore_patterns(".git"))
    log = bundle_root / "check-suite-output.txt"
    log.write_text(
        "\n".join(
            [
                f"команда: {' '.join(command)}",
                f"код возврата: {result['exit_code']}",
                "",
                "--- stdout ---",
                result["stdout"],
                "--- stderr ---",
                result["stderr"],
            ]
        ),
        encoding="utf-8",
    )

    envelope["artifacts"] = [
        artifact
        for artifact in envelope["artifacts"]
        if artifact["id"] not in {SUITE_ARTIFACT, SUITE_LOG_ARTIFACT}
    ]
    envelope["artifacts"].append(
        directory_artifact(
            SUITE_ARTIFACT, "EVIDENCE", stored, bundle_root, SUITE_MEDIA_TYPE
        )
    )
    envelope["artifacts"].append(
        file_artifact(SUITE_LOG_ARTIFACT, "LOG", log, bundle_root, "text/plain")
    )
    replace_evaluation(
        envelope,
        suite_evaluation(
            evaluation_id="suite",
            result=result,
            subject_artifact_id=subject,
            evidence_artifact_ids=[SUITE_ARTIFACT, SUITE_LOG_ARTIFACT],
        ),
    )


Evaluator = Callable[[dict[str, Any], Path, dict[str, Any]], None]

EVALUATORS: dict[str, Evaluator] = {
    "citations": attach_citations,
    "completeness": attach_completeness,
    "mentions": attach_mentions,
    "claims": attach_claims,
    "suite": attach_suite,
}

Validator = Callable[[dict[str, Any], Path, Path | None], None]

# Some evaluations can be refused before a run rather than after: a suite that
# does not exist, or that the executor would have seen, is a mistake in the
# description and costs nothing to catch there.
VALIDATORS: dict[str, Validator] = {
    "suite": check_suite_options,
}


def unknown_names(evaluate: dict[str, Any]) -> list[str]:
    """Names in a description that no evaluator answers to."""
    return sorted(name for name in evaluate if name not in EVALUATORS)


def attach_all(
    envelope: dict[str, Any], bundle_root: Path, evaluate: dict[str, Any]
) -> None:
    """Run every evaluation the description asked for, in a stable order."""
    for name in sorted(evaluate):
        evaluator = EVALUATORS.get(name)
        if evaluator is None:
            raise ValueError(f"неизвестная оценка: {name}")
        evaluator(envelope, bundle_root, options_for(evaluate[name]))

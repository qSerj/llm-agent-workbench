"""Measure a run against a check suite the executor never saw.

A reference answer is expressed as checks rather than as a model document: a
good reference document unfolds into a list of statements anyway, so let it be
code from the start, versioned next to the example. The form suits code and
documentation alike.

The suite is hidden by *absence*, not by permission. It is not in the workspace
while the candidate works; it is laid over a copy afterwards, the way SWE-bench
hands the executor the state before the fix and applies the tests separately. No
permission machinery is needed, and none is claimed.

Two things are said plainly rather than hidden:

* the suite runs with the privileges of whoever runs the evaluation, not inside
  the opencode sandbox a stage gets — it is trusted code from the repository,
  the same trust a test suite already has;
* the whole suite is one ``CODE`` evaluation. A suite that asked a model
  something would need its own kind of evidence, and that field is added when a
  run needs it, not before (ADR 0006).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from workbench.judge import verdict_for
from workbench.modelreply import extract_json

POLICY = {"id": "hidden-check-suite", "version": "1"}
SUITE_MEDIA_TYPE = "application/vnd.workbench.check-suite"
DEFAULT_TIMEOUT = 600
OUTCOMES = ("PASS", "FAIL", "UNDETERMINED")


def suite_path(options: dict[str, Any], root: Path) -> Path:
    """Where the suite lives: repository-relative, like ``workspace:`` itself."""
    raw = str(options.get("path") or "")
    if not raw:
        raise ValueError("оценке suite нужен путь path к каталогу проверок")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def suite_command(options: dict[str, Any]) -> list[str]:
    """The command, always an explicit argument list — never a shell string."""
    raw = options.get("command")
    if not isinstance(raw, list) or not raw or not all(isinstance(x, str) for x in raw):
        raise ValueError("оценке suite нужен command — непустой список строк")
    return [str(item) for item in raw]


def suite_timeout(options: dict[str, Any]) -> int:
    value = options.get("timeout", DEFAULT_TIMEOUT)
    try:
        seconds = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("timeout оценки suite должен быть целым числом секунд") from error
    if seconds <= 0:
        raise ValueError("timeout оценки suite должен быть больше нуля")
    return seconds


def check_suite_options(
    options: dict[str, Any], root: Path, workspace: Path | None
) -> None:
    """Refuse a suite that cannot run, or that the executor would have seen.

    Checked while the description is read, before anything is spent: the same
    place that already refuses an evaluation nobody implements.
    """
    path = suite_path(options, root)
    suite_command(options)
    suite_timeout(options)
    if not path.is_dir():
        raise ValueError(f"каталог проверок не найден: {path}")
    if workspace is None:
        return
    workspace = workspace.resolve()
    if path.is_relative_to(workspace) or workspace.is_relative_to(path):
        raise ValueError(
            f"набор проверок {path} лежит внутри рабочего пространства {workspace}: "
            "исполнитель увидел бы его во время работы"
        )


def normalise_checks(raw: Any) -> list[dict[str, Any]]:
    """Read what the suite printed, turning anything unclear into UNDETERMINED."""
    checks: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return checks
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or f"проверка {index}")
        outcome = str(item.get("outcome", "")).upper()
        value = item.get("value")
        if not isinstance(value, (int, float, str, bool)) and value is not None:
            value = str(value)
        checks.append(
            {
                "id": identifier[:200],
                "outcome": outcome if outcome in OUTCOMES else "UNDETERMINED",
                "value": value,
                "rationale": str(item.get("rationale") or ""),
            }
        )
    return checks


def run_suite(
    workspace: Path, suite: Path, command: list[str], timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Lay the suite over a copy of the workspace, run it, and read its answer.

    The workspace itself is never touched: a stored run is a record whose
    artifacts are checksummed, and it must not gain a check file or a trace of
    one having run.
    """
    scratch = Path(tempfile.mkdtemp(prefix="workbench-suite-"))
    copy = scratch / "workspace"
    try:
        shutil.copytree(workspace, copy, ignore=shutil.ignore_patterns(".git"))
        # The suite wins over the workspace: a candidate that wrote a file with
        # the same name cannot displace the check that judges it.
        shutil.copytree(
            suite, copy, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git")
        )
        try:
            completed = subprocess.run(
                command,
                cwd=copy,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout, stderr, exit_code = (
                completed.stdout,
                completed.stderr,
                completed.returncode,
            )
            timed_out = False
        except subprocess.TimeoutExpired as expired:
            stdout = expired.stdout or ""
            stderr = expired.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            exit_code = None
            timed_out = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    problem: str | None = None
    checks: list[dict[str, Any]] = []
    if timed_out:
        problem = f"набор проверок не уложился в {timeout} с"
    else:
        try:
            answer = extract_json(stdout, "набора проверок")
        except (ValueError, json.JSONDecodeError) as error:
            # An answer nobody can read is not a failure of the work and not a
            # clean bill either: it says nothing (ADR 0004).
            problem = f"вывод набора не разобран: {error}"
        else:
            checks = normalise_checks(answer.get("checks"))
            if not checks:
                problem = "набор не сообщил ни одной проверки"

    return {
        "verdict": verdict_for(checks),
        "checks": checks,
        "exit_code": exit_code,
        "problem": problem,
        "stdout": stdout,
        "stderr": stderr,
    }


def suite_rationale(result: dict[str, Any]) -> str:
    if result["problem"]:
        return result["problem"]
    checks = result["checks"]
    failed = sum(1 for item in checks if item["outcome"] == "FAIL")
    unknown = sum(1 for item in checks if item["outcome"] == "UNDETERMINED")
    return (
        f"проверок {len(checks)}: не пройдено {failed}, "
        f"без ответа {unknown}"
    )


def suite_evaluation(
    evaluation_id: str,
    result: dict[str, Any],
    subject_artifact_id: str,
    evidence_artifact_ids: list[str],
) -> dict[str, Any]:
    """Wrap a suite run as a ``CODE`` evaluation for an envelope."""
    return {
        "id": evaluation_id,
        "subject": {"kind": "ARTIFACT", "id": subject_artifact_id},
        "evaluator": {"source": "CODE", "identity": "workbench.suite"},
        "policy": dict(POLICY),
        "result": {"verdict": result["verdict"], "checks": result["checks"]},
        "rationale": suite_rationale(result),
        "evidence_artifact_ids": list(evidence_artifact_ids),
    }

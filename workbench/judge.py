"""Have a model read the sources and say whether the document tells the truth.

This is the half of documentation quality a program cannot reach. Whether a name
is absent can be derived (``workbench.inventory``); whether a sentence about
``ToRegisters()`` is *true* cannot, short of understanding both the sentence and
the code. So the judgement is asked of a model — and recorded as ``LLM_JUDGE``,
never mixed with what a program established.

Two properties are load-bearing:

* the judge reads the sources itself, so its verdict rests on the material
  rather than on the document's own account of it;
* what judging cost is reported separately from what the candidate cost. The
  price of measuring is not part of the price of the work.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from workbench.modelreply import ask_model, extract_json

# The judge must read the workspace and must not change it. Denying bash as well
# keeps the verdict a reading of the sources rather than of a program's output.
JUDGE_PERMISSIONS = {
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "list": "allow",
    "lsp": "allow",
    "edit": "deny",
    "bash": "deny",
    "webfetch": "deny",
    "websearch": "deny",
}

POLICY = {"id": "claims-against-sources", "version": "1"}

# The model's own words for an outcome, mapped to the envelope's three.
OUTCOMES = {
    "SUPPORTED": "PASS",
    "CONTRADICTED": "FAIL",
    "UNSUPPORTED": "UNDETERMINED",
}

INSTRUCTIONS = """\
Ты — проверяющий фактическую точность технической документации. В рабочем
каталоге лежат исходники и документ {document}. Исходники — источник истины;
сам документ источником истины не является.

Прочитай документ, раздели его на отдельные проверяемые утверждения о коде и по
каждому вынеси суждение, сверяясь с исходниками. Читай файлы сам.

Ответь ОДНИМ объектом JSON и ничем больше:

{{
  "claims": [
    {{
      "claim": "утверждение своими словами, коротко",
      "outcome": "SUPPORTED | CONTRADICTED | UNSUPPORTED",
      "evidence": "путь/к/файлу.cs:строка",
      "rationale": "чем именно исходники подтверждают или опровергают"
    }}
  ]
}}

Значения outcome:
- SUPPORTED — исходники прямо подтверждают утверждение;
- CONTRADICTED — исходники говорят обратное; это ошибка в документе;
- UNSUPPORTED — в исходниках нет ни подтверждения, ни опровержения; сюда же
  относится выдуманное поведение, которого в коде просто нет.

Не оценивай стиль, полноту и оформление — только истинность сказанного.
Не предлагай исправлений. Утверждений обычно от 10 до 40.
"""


def judge_document(
    workspace: Path,
    document_relative: str,
    model: str,
    provider: str = "openrouter",
    base_url: str | None = None,
    opencode: str = "opencode",
    heartbeat: int = 30,
) -> dict[str, Any]:
    """Ask a model to rule on every claim, and report what the ruling cost.

    The workspace is copied first. A stored run is a record whose artifacts are
    checksummed; judging must not leave a configuration file or a log inside it.
    """
    scratch = Path(tempfile.mkdtemp(prefix="workbench-judge-"))
    copy = scratch / "workspace"
    try:
        shutil.copytree(workspace, copy, ignore=shutil.ignore_patterns(".git"))
        answer = ask_model(
            INSTRUCTIONS.format(document=document_relative),
            model=model,
            provider=provider,
            base_url=base_url,
            permission=JUDGE_PERMISSIONS,
            directory=copy,
            opencode=opencode,
            heartbeat=heartbeat,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if answer["exit_code"] != 0 and not answer["text"]:
        raise ValueError(f"судья завершился с кодом {answer['exit_code']}")
    document = extract_json(answer["text"], "судьи")
    return {"claims": document.get("claims") or [], **answer}


def checks_from_claims(claims: list[Any]) -> list[dict[str, Any]]:
    """Turn what the judge said into checks, dropping nothing silently.

    A claim the judge labelled with a word we do not know becomes UNDETERMINED
    rather than disappearing: an unreadable answer is not a clean bill.
    """
    checks: list[dict[str, Any]] = []
    for index, raw in enumerate(claims, start=1):
        if not isinstance(raw, dict):
            continue
        claim = str(raw.get("claim") or f"утверждение {index}")
        outcome = OUTCOMES.get(str(raw.get("outcome", "")).upper(), "UNDETERMINED")
        evidence = str(raw.get("evidence") or "")
        rationale = str(raw.get("rationale") or "")
        checks.append(
            {
                "id": claim[:200],
                "outcome": outcome,
                "value": evidence or None,
                "rationale": rationale,
            }
        )
    return checks


def verdict_for(checks: list[dict[str, Any]]) -> str:
    """One contradiction is enough to fail: an invented fact is not averaged away."""
    if not checks:
        return "UNDETERMINED"
    if any(item["outcome"] == "FAIL" for item in checks):
        return "FAIL"
    if all(item["outcome"] == "PASS" for item in checks):
        return "PASS"
    return "UNDETERMINED"


def claims_evaluation(
    evaluation_id: str,
    ruling: dict[str, Any],
    provider: str,
    subject_artifact_id: str,
    evidence_artifact_ids: list[str],
) -> dict[str, Any]:
    """Wrap a ruling as an envelope evaluation, naming who ruled."""
    checks = checks_from_claims(ruling["claims"])
    verdict = verdict_for(checks)
    contradicted = sum(1 for item in checks if item["outcome"] == "FAIL")
    unsupported = sum(1 for item in checks if item["outcome"] == "UNDETERMINED")
    if not checks:
        rationale = "судья не выделил ни одного проверяемого утверждения"
    else:
        rationale = (
            f"утверждений {len(checks)}: опровергнуто {contradicted}, "
            f"не подтверждено {unsupported}"
        )
    return {
        "id": evaluation_id,
        "subject": {"kind": "ARTIFACT", "id": subject_artifact_id},
        "evaluator": {
            "source": "LLM_JUDGE",
            "identity": "workbench.judge",
            "provider": provider,
            "model": ruling["model"],
        },
        "policy": dict(POLICY),
        "result": {"verdict": verdict, "checks": checks},
        "rationale": rationale,
        "evidence_artifact_ids": list(evidence_artifact_ids),
    }

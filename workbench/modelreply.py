"""Ask a model for one JSON answer through OpenCode, and read the answer back.

Shared by everything in the project that wants a model to *say* something rather
than to change a workspace: drafting an experiment, judging a document. Going
through OpenCode rather than an HTTP client of our own means such a model is
chosen exactly the way a stage's model is chosen — ``provider`` plus ``model`` —
so OpenRouter, LM Studio and Ollama work without a second credential path, and
what the call cost is measured by the same code that measures a stage.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from workbench.chain import (
    StageSpec,
    build_opencode_config,
    collect_usage_from_jsonl,
    stream_opencode,
)

FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

# Nothing may be touched or fetched. A caller that needs the model to read a
# workspace passes its own permissions instead.
SILENT_PERMISSIONS = {
    "read": "deny",
    "glob": "deny",
    "grep": "deny",
    "list": "deny",
    "edit": "deny",
    "bash": "deny",
    "webfetch": "deny",
    "websearch": "deny",
}


def extract_json(text: str, whose: str = "модели") -> dict[str, Any]:
    """Read the object out of a reply that may be wrapped in prose or a fence."""
    match = FENCE.search(text)
    if match:
        return json.loads(match.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"в ответе {whose} нет объекта JSON")
    return json.loads(text[start : end + 1])


def reply_text(log_path: Path) -> str:
    """Concatenate what the model said, ignoring its tool and step events."""
    said: list[str] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            said.append(str((event.get("part") or {}).get("text", "")))
    return "\n".join(said)


def ask_model(
    prompt: str,
    model: str,
    provider: str = "openrouter",
    base_url: str | None = None,
    permission: dict[str, Any] | None = None,
    directory: Path | None = None,
    opencode: str = "opencode",
    heartbeat: int = 30,
) -> dict[str, Any]:
    """Put one question to a model and return its words together with the cost.

    ``directory`` is what the model is pointed at. Given none, it works in an
    empty scratch directory that is removed afterwards — the right choice when
    the material is already in the prompt. Given one, that directory is used as
    is and left alone, so the caller stays in charge of what may be read.
    """
    spec = StageSpec(
        role="OTHER",
        model=model,
        prompt=Path("(asked directly)"),
        allow_edit=[],
        provider=provider,
        base_url=base_url,
    )
    config, model_name = build_opencode_config(
        spec, permission=permission or SILENT_PERMISSIONS
    )

    scratch = directory or Path(tempfile.mkdtemp(prefix="workbench-ask-"))
    disposable = directory is None
    previous = scratch / "opencode.json"
    kept = previous.read_text(encoding="utf-8") if previous.is_file() else None
    try:
        previous.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log_path = scratch / "opencode.jsonl"
        exit_code, wall_seconds = stream_opencode(
            [
                opencode,
                "run",
                "--format",
                "json",
                "--model",
                model_name,
                "--dir",
                str(scratch),
                prompt,
            ],
            cwd=scratch,
            log_path=log_path,
            heartbeat=heartbeat,
        )
        usage = collect_usage_from_jsonl(log_path)
        text = reply_text(log_path)
    finally:
        if disposable:
            shutil.rmtree(scratch, ignore_errors=True)
        elif kept is not None:
            previous.write_text(kept, encoding="utf-8")

    return {
        "text": text,
        "model": model_name,
        "exit_code": exit_code,
        "wall_seconds": wall_seconds,
        "api_cost_usd": usage.get("api_cost_usd"),
    }

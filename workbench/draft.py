"""Turn a plain-language description of an intent into a draft experiment.

The draft is a proposal, never a fact: it is shown to a person, edited, and only
written to disk when they say so. Nothing here decides anything about a run.

The model is reached through OpenCode rather than through an HTTP client of our
own. That is not laziness — it means the drafting model is chosen exactly the
way a stage's model is chosen (``provider`` plus ``model``), so OpenRouter, LM
Studio and Ollama all work without a second credential path, and the cost of
drafting is measured by the same code that measures a stage.
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

# The drafting model writes a proposal and touches nothing: it is handed the
# workspace as text, never as a directory it may open.
DRAFT_PERMISSIONS = {
    "read": "deny",
    "glob": "deny",
    "grep": "deny",
    "list": "deny",
    "edit": "deny",
    "bash": "deny",
    "webfetch": "deny",
    "websearch": "deny",
}

MAX_TREE_ENTRIES = 300
FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

INSTRUCTIONS = """\
Ты помогаешь исследователю подготовить заготовку эксперимента, который сравнивает
несколько способов решения одной задачи над одним репозиторием.

Ответь ОДНИМ объектом JSON и ничем больше. Схема:

{
  "id": "короткое-имя-в-дефисах",
  "question": "исследовательский вопрос одной фразой, по-русски",
  "task": "короткое-имя-задачи",
  "evaluate": {"citations": "путь/к/итоговому/документу.md"},
  "candidates": [
    {"id": "single", "stages": [
      {"role": "SOLVER", "model": "", "prompt": "task.md",
       "allow_edit": ["docs/result.md"]}
    ]}
  ],
  "prompts": {"task.md": "текст промпта", "reviewer.md": "текст промпта"}
}

Правила:
- роли только SOLVER, REVIEWER, FIXER, OTHER; цепочка — последовательность,
  рабочее пространство следующего этапа это выход предыдущего;
- предложи 2-3 способа: одиночного исполнителя и хотя бы одну цепочку, чтобы
  было что с чем сравнивать;
- "prompt" — имя файла из "prompts", без каталогов;
- "allow_edit" — точные пути внутри рабочего пространства, которые этап меняет;
  шаблоны запрещены, каждый этап меняет только своё;
- "model" оставь пустой строкой: модель выберет человек;
- "evaluate.citations" указывай только если результат — документ, в котором
  уместны ссылки вида путь:строка; иначе не указывай evaluate вовсе;
- промпты пиши на том же языке, что и описание исследователя.
"""


def file_tree(workspace: Path, limit: int = MAX_TREE_ENTRIES) -> str:
    """A flat listing of the workspace, so paths in the draft are real ones."""
    if not workspace.is_dir():
        return "(рабочее пространство недоступно)"
    found: list[str] = []
    for path in sorted(workspace.rglob("*")):
        if any(part.startswith(".") for part in path.parts):
            continue
        if path.is_file():
            found.append(str(path.relative_to(workspace)))
        if len(found) >= limit:
            found.append(f"… список обрезан на {limit} файлах")
            break
    return "\n".join(found) or "(пусто)"


def readme_of(workspace: Path, limit: int = 4000) -> str:
    for name in ("README.md", "README.txt", "readme.md"):
        candidate = workspace / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace")[:limit]
    return ""


def build_prompt(description: str, success: str, workspace: Path) -> str:
    """Everything the drafting model is given: the intent and what is there."""
    readme = readme_of(workspace)
    parts = [
        INSTRUCTIONS,
        "## Что исследователь хочет проверить\n\n" + description.strip(),
    ]
    if success.strip():
        parts.append("## Что считать хорошим результатом\n\n" + success.strip())
    parts.append(f"## Рабочее пространство: {workspace}\n\n```\n{file_tree(workspace)}\n```")
    if readme:
        parts.append("## README рабочего пространства\n\n" + readme)
    return "\n\n".join(parts)


def extract_json(text: str) -> dict[str, Any]:
    """Read the object out of a reply that may be wrapped in prose or a fence."""
    match = FENCE.search(text)
    if match:
        return json.loads(match.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("в ответе составителя нет объекта JSON")
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


def draft_experiment(
    description: str,
    success: str,
    workspace: Path,
    model: str,
    provider: str = "openrouter",
    base_url: str | None = None,
    opencode: str = "opencode",
    heartbeat: int = 30,
) -> dict[str, Any]:
    """Ask a model for a draft and return it with what it cost to obtain.

    The model runs in an empty directory with every tool denied: it is here to
    write a proposal, not to touch the workspace it is describing.
    """
    spec = StageSpec(
        role="OTHER",
        model=model,
        prompt=Path("(draft)"),
        allow_edit=[],
        provider=provider,
        base_url=base_url,
    )
    config, model_name = build_opencode_config(spec, permission=DRAFT_PERMISSIONS)

    scratch = Path(tempfile.mkdtemp(prefix="workbench-draft-"))
    try:
        (scratch / "opencode.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log_path = scratch / "opencode.jsonl"
        prompt = build_prompt(description, success, workspace)
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
        shutil.rmtree(scratch, ignore_errors=True)

    if exit_code != 0 and not text:
        raise ValueError(f"составитель завершился с кодом {exit_code}")

    document = extract_json(text)
    prompts = {
        str(name): str(body) for name, body in (document.pop("prompts", {}) or {}).items()
    }
    if not prompts:
        raise ValueError("составитель не предложил ни одного промпта")

    return {
        "document": document,
        "prompts": prompts,
        "model": model_name,
        "wall_seconds": wall_seconds,
        "api_cost_usd": usage.get("api_cost_usd"),
    }

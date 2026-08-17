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

from pathlib import Path
from typing import Any

from workbench.modelreply import SILENT_PERMISSIONS, ask_model, extract_json

# The drafting model writes a proposal and touches nothing: it is handed the
# workspace as text, never as a directory it may open.
DRAFT_PERMISSIONS = SILENT_PERMISSIONS

MAX_TREE_ENTRIES = 300

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
    answer = ask_model(
        build_prompt(description, success, workspace),
        model=model,
        provider=provider,
        base_url=base_url,
        permission=DRAFT_PERMISSIONS,
        opencode=opencode,
        heartbeat=heartbeat,
    )
    if answer["exit_code"] != 0 and not answer["text"]:
        raise ValueError(f"составитель завершился с кодом {answer['exit_code']}")

    document = extract_json(answer["text"], "составителя")
    prompts = {
        str(name): str(body) for name, body in (document.pop("prompts", {}) or {}).items()
    }
    if not prompts:
        raise ValueError("составитель не предложил ни одного промпта")

    return {
        "document": document,
        "prompts": prompts,
        "model": answer["model"],
        "wall_seconds": answer["wall_seconds"],
        "api_cost_usd": answer["api_cost_usd"],
    }

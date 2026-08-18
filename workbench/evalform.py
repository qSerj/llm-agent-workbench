"""What each evaluation's settings look like in a form, and how they survive it.

The shell used to show one evaluation out of five, and saving a description
rebuilt ``evaluate:`` out of the posted fields alone — so everything the form
did not draw was silently dropped. This module is the answer: the registry
describes its own settings, the form is generated from that description, and
whatever the description does not cover is carried through untouched rather than
thrown away. The shell edits intent; losing intent is not an edit.

It lives apart from ``workbench.evaluators`` on purpose. That module imports the
judge, which imports OpenCode plumbing (subprocess, threading); this one is data
and string handling, so the editor, the tests and any future tool can use it
without dragging a process runner behind them. The two registries are kept in
step by a test, not by sharing a file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Posted by the editor so that clearing every checkbox reads as "measure
# nothing" rather than as "these fields came from somewhere else".
FORM_MARKER = "evaluate.form"

TEXT = "text"
LIST = "list"
INT = "int"


@dataclass(frozen=True)
class Option:
    """One setting of one evaluation, as the form shows it."""

    name: str
    label: str
    kind: str = TEXT
    hint: str = ""
    required: bool = False


@dataclass(frozen=True)
class EvaluatorForm:
    """An evaluation as the form shows it: what it measures and what it needs.

    ``summary`` says what the evaluation does **and does not** establish. A
    person choosing a measurement in a browser has no other place to learn that
    a citation check measures citing discipline rather than truthfulness.
    """

    name: str
    title: str
    summary: str
    options: tuple[Option, ...]
    spends_money: bool = False


DOCUMENT = Option(
    name="document",
    label="Документ",
    hint="Путь внутри рабочего пространства к итоговому документу.",
    required=True,
)

LANGUAGE = Option(
    name="language",
    label="Язык исходников",
    hint="Пока разбирается только csharp. Пусто — csharp.",
)

EVALUATOR_FORMS: dict[str, EvaluatorForm] = {
    "citations": EvaluatorForm(
        name="citations",
        title="Ссылки на строки",
        summary=(
            "Проверяет, что каждая ссылка вида путь:строка указывает на "
            "существующую строку. Это дисциплина цитирования, а не правдивость: "
            "документ из одних выдумок с исправными ссылками получит PASS."
        ),
        options=(DOCUMENT,),
    ),
    "completeness": EvaluatorForm(
        name="completeness",
        title="Полнота по перечню имён",
        summary=(
            "Выводит из исходников перечень публичных имён и смотрит, все ли "
            "упомянуты в документе. Ничего не говорит о том, верно ли сказанное."
        ),
        options=(DOCUMENT, LANGUAGE),
    ),
    "mentions": EvaluatorForm(
        name="mentions",
        title="Выдуманные имена",
        summary=(
            "Обратный ход к полноте: всякое имя, поданное документом как код, "
            "должно встречаться в исходниках. Ловит выдуманный идентификатор, "
            "но не выдуманное утверждение — это разные беды."
        ),
        options=(DOCUMENT, LANGUAGE),
    ),
    "claims": EvaluatorForm(
        name="claims",
        title="Правдивость утверждений (судья-модель)",
        summary=(
            "Модель читает исходники сама и судит каждое утверждение документа. "
            "Единственная оценка здесь, которая тратит деньги; её цена "
            "записывается отдельно и в цену способа не входит."
        ),
        options=(
            DOCUMENT,
            Option(
                name="model",
                label="Модель-судья",
                hint="Например, deepseek/deepseek-v4-flash.",
                required=True,
            ),
            Option(name="provider", label="Провайдер", hint="Пусто — openrouter."),
            Option(name="base_url", label="Адрес API", hint="Только для своего сервера."),
        ),
        spends_money=True,
    ),
    "suite": EvaluatorForm(
        name="suite",
        title="Скрытый набор проверок",
        summary=(
            "Заранее известный правильный результат, выраженный проверками. "
            "Каталог должен лежать ВНЕ рабочего пространства: исполнитель его не "
            "видит, набор накладывается на копию после прогона. Набор печатает "
            "один JSON и исполняется с вашими правами, вне песочницы."
        ),
        options=(
            Option(
                name="path",
                label="Каталог проверок",
                hint="Путь от корня репозитория, рядом с промптами, вне workspace.",
                required=True,
            ),
            Option(
                name="command",
                label="Команда",
                kind=LIST,
                hint="Через запятую, как аргументы: python3, run_checks.py",
                required=True,
            ),
            Option(
                name="timeout",
                label="Предел времени, с",
                kind=INT,
                hint="Пусто — 600.",
            ),
        ),
    ),
}


def option_text(value: Any) -> str:
    """Show a stored value in a single text input."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def option_from_text(kind: str, text: str) -> Any:
    """Read a value back. What cannot be read is passed on, not repaired.

    A timeout of ``вчера`` stays ``вчера`` so that ``suite_timeout`` says what
    is wrong with it. A form that quietly substituted a zero would turn a typo
    into a measurement.
    """
    text = text.strip()
    if not text:
        return None
    if kind == LIST:
        return [item.strip() for item in text.split(",") if item.strip()]
    if kind == INT:
        try:
            return int(text)
        except ValueError:
            return text
    return text


def kind_of(value: Any) -> str:
    """The kind a stored value looks like, for a setting nobody declared."""
    if isinstance(value, list):
        return LIST
    if isinstance(value, bool):
        return TEXT
    if isinstance(value, int):
        return INT
    return TEXT


def declared(name: str) -> dict[str, Option]:
    form = EVALUATOR_FORMS.get(name)
    return {item.name: item for item in form.options} if form else {}


def form_rows(name: str, options: dict[str, Any]) -> list[dict[str, Any]]:
    """The visible fields: stored keys first, in the order the file has them.

    Order is load-bearing. ``dump_experiment`` writes options in insertion
    order, so rendering in the declared order instead would rearrange every
    hand-written block on its first save.
    """
    known = declared(name)
    rows: list[dict[str, Any]] = []
    for key, value in options.items():
        option = known.get(key)
        if option is None:
            continue
        rows.append(
            {
                "field": f"evaluate.{name}.{key}",
                "option": option,
                "value": option_text(value),
            }
        )
    seen = {row["option"].name for row in rows}
    for key, option in known.items():
        if key not in seen:
            rows.append(
                {"field": f"evaluate.{name}.{key}", "option": option, "value": ""}
            )
    return rows


def hidden_rows(name: str, options: dict[str, Any]) -> list[dict[str, Any]]:
    """Settings this form does not describe, carried through as they are.

    Each one goes back with a companion field naming its kind, so a list
    written by hand does not come back a string.
    """
    known = declared(name)
    return [
        {
            "field": f"evaluate.{name}.{key}",
            "kind_field": f"kind.evaluate.{name}.{key}",
            "kind": kind_of(value),
            "name": key,
            "value": option_text(value),
        }
        for key, value in options.items()
        if key not in known
    ]


def evaluate_form_fields(evaluate: dict[str, Any]) -> dict[str, list[str]]:
    """The fields a form would post for this registry — the inverse of reading.

    Used by the tests to close the circle without a browser.
    """
    fields: dict[str, list[str]] = {FORM_MARKER: ["1"]}
    for name, options in evaluate.items():
        fields[f"evaluate.{name}.on"] = ["1"]
        for row in form_rows(name, options):
            fields[row["field"]] = [row["value"]]
        for row in hidden_rows(name, options):
            fields[row["field"]] = [row["value"]]
            fields[row["kind_field"]] = [row["kind"]]
    return fields


def evaluate_from_fields(fields: dict[str, list[str]]) -> dict[str, Any]:
    """Read the registry back out of flat form fields.

    An evaluation is written when its checkbox is on. Its settings keep the
    order they were posted in, so a description written by hand comes back in
    its own order.
    """
    enabled: list[str] = []
    values: dict[str, dict[str, Any]] = {}
    for key, posted in fields.items():
        if not key.startswith("evaluate."):
            continue
        rest = key[len("evaluate.") :]
        name, _, option = rest.partition(".")
        if not name:
            continue
        if option == "on":
            if posted and posted[0].strip():
                enabled.append(name)
            continue
        if not option:
            # ``evaluate.citations`` on its own is the old shorthand: a plain
            # path meaning the document. Still accepted so an old form, or a
            # hand-made request, keeps working.
            option = "document"
        kind = declared(name).get(option)
        kind_name = kind.kind if kind else (fields.get(f"kind.{key}") or [TEXT])[0]
        value = option_from_text(kind_name, posted[0] if posted else "")
        if value is None:
            continue
        values.setdefault(name, {})[option] = value

    # A browser posts nothing for a cleared checkbox, so "no checkbox arrived"
    # is ambiguous on its own: it means both "the form turned everything off"
    # and "these fields did not come from the form at all". The form says which
    # by always posting FORM_MARKER.
    if FORM_MARKER in fields:
        return {name: values[name] for name in enabled if values.get(name)}
    return {name: options for name, options in values.items() if options}


def paid_names(evaluate: dict[str, Any], only: list[str] | None = None) -> list[str]:
    """Which of the chosen evaluations spend money."""
    chosen = list(evaluate) if only is None else [n for n in only if n in evaluate]
    return [
        name
        for name in chosen
        if name in EVALUATOR_FORMS and EVALUATOR_FORMS[name].spends_money
    ]


def confirmations(evaluate: dict[str, Any], only: list[str]) -> list[dict[str, str]]:
    """What a person must be told before a paid evaluation is started."""
    found: list[dict[str, str]] = []
    for name in paid_names(evaluate, only):
        options = evaluate.get(name) or {}
        found.append(
            {
                "name": name,
                "model": str(options.get("model") or ""),
                "provider": str(options.get("provider") or "openrouter"),
            }
        )
    return found

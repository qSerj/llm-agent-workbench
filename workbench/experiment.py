"""Read and write a short experiment description, and turn it into candidates.

The description is deliberately small: a human question, the workspace under
test, and the candidates being compared. A field is added when a real run needed
it, not because a hypothetical scenario might.

Writing is here rather than in the shell so that both directions stay covered by
the offline tests: CI installs ``requirements-lab.txt`` only, and the shell's web
stack is not part of it.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workbench.chain import StageSpec

STAGE_ROLES = {"SOLVER", "REVIEWER", "FIXER", "OTHER"}

# The width hand-written descriptions already wrap to.
LINE_WIDTH = 80


@dataclass
class CandidateSpec:
    id: str
    stages: list[StageSpec]


@dataclass
class Experiment:
    id: str
    question: str
    workspace: Path
    task: dict[str, str]
    case: dict[str, str]
    candidates: list[CandidateSpec]
    repetitions: int = 1
    evaluate: dict[str, Any] = field(default_factory=dict)

    def candidate(self, candidate_id: str) -> CandidateSpec:
        for item in self.candidates:
            if item.id == candidate_id:
                return item
        known = ", ".join(item.id for item in self.candidates)
        raise KeyError(f"unknown candidate {candidate_id}; known: {known}")


def read_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError(
            "reading an experiment requires PyYAML; see requirements-lab.txt"
        ) from error
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def versioned_reference(value: Any, field_name: str) -> dict[str, str]:
    """Accept either ``name`` or ``{id: name, version: "2"}``.

    An empty name is not a name: it would write a reference that cannot be read
    back, which is worse than refusing it here.
    """
    if isinstance(value, str) and value:
        return {"id": value, "version": "1"}
    if isinstance(value, dict) and "id" in value:
        return {"id": str(value["id"]), "version": str(value.get("version", "1"))}
    raise ValueError(f"{field_name} must be a name or a mapping with an id")


def parse_stage(raw: Any, position: int, candidate_id: str) -> StageSpec:
    where = f"candidate {candidate_id}, stage {position}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: a stage must be a mapping")
    missing = {"role", "model", "prompt", "allow_edit"} - set(raw)
    if missing:
        raise ValueError(f"{where}: missing {', '.join(sorted(missing))}")

    role = str(raw["role"]).upper()
    if role not in STAGE_ROLES:
        raise ValueError(
            f"{where}: role must be one of {', '.join(sorted(STAGE_ROLES))}"
        )
    allow_edit = raw["allow_edit"]
    if not isinstance(allow_edit, list) or not allow_edit:
        raise ValueError(f"{where}: allow_edit must be a non-empty list")

    return StageSpec(
        role=role,
        model=str(raw["model"]),
        prompt=Path(str(raw["prompt"])),
        allow_edit=[str(item) for item in allow_edit],
        provider=str(raw.get("provider", "openrouter")),
        base_url=raw.get("base_url"),
        api_key_env=raw.get("api_key_env"),
    )


def load_experiment(path: Path, root: Path | None = None) -> Experiment:
    """Load an experiment, resolving relative paths against ``root``."""
    return parse_experiment(read_yaml(path), root=root, where=str(path))


def parse_experiment(
    document: Any, root: Path | None = None, where: str = "experiment"
) -> Experiment:
    """Validate a description already in memory, resolving paths against ``root``.

    Kept separate from ``load_experiment`` so an editor can check a draft before
    anything reaches the disk.
    """
    root = (root or Path.cwd()).resolve()
    path = where
    if not isinstance(document, dict):
        raise ValueError(f"{path}: an experiment must be a mapping")

    missing = {"id", "question", "workspace", "candidates"} - set(document)
    if missing:
        raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")

    raw_candidates = document["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError(f"{path}: candidates must be a non-empty list")

    candidates: list[CandidateSpec] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict) or "id" not in raw:
            raise ValueError(f"{path}: every candidate needs an id")
        candidate_id = str(raw["id"])
        stages = raw.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError(f"candidate {candidate_id}: stages must be a non-empty list")
        parsed = [
            parse_stage(stage, position, candidate_id)
            for position, stage in enumerate(stages, start=1)
        ]
        for stage in parsed:
            stage.prompt = (root / stage.prompt).resolve()
            if not stage.prompt.is_file():
                raise ValueError(f"candidate {candidate_id}: no prompt {stage.prompt}")
        candidates.append(CandidateSpec(id=candidate_id, stages=parsed))

    identifiers = [item.id for item in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{path}: candidate ids must be unique")

    workspace = (root / str(document["workspace"])).resolve()
    if not workspace.is_dir():
        raise ValueError(f"{path}: no workspace directory {workspace}")

    repetitions = int(document.get("repetitions", 1))
    if repetitions < 1:
        raise ValueError(f"{path}: repetitions must be at least 1")

    experiment_id = str(document["id"])
    return Experiment(
        id=experiment_id,
        question=str(document["question"]),
        workspace=workspace,
        task=versioned_reference(document.get("task", experiment_id), "task"),
        case=versioned_reference(document.get("case", workspace.name), "case"),
        candidates=candidates,
        repetitions=repetitions,
        evaluate=parse_evaluate(
            document.get("evaluate"), path, root=root, workspace=workspace
        ),
    )


def parse_evaluate(
    raw: Any,
    where: str,
    root: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Read the evaluation registry: a name picks an evaluator, the value tunes it.

    A name nothing answers to is refused here rather than dropped, so an
    experiment that asks for a measurement it will not get fails before it runs
    and spends money. Some evaluators can say more than that about their own
    settings — a hidden check suite must exist and must lie outside the
    workspace — and say it through ``VALIDATORS`` at the same early moment. The
    checks live behind a late import because the evaluators reach back into this
    module.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: evaluate must be a mapping")

    from workbench.evaluators import VALIDATORS, options_for, unknown_names

    evaluate: dict[str, Any] = {}
    for name, value in raw.items():
        try:
            evaluate[str(name)] = options_for(value)
        except ValueError as error:
            raise ValueError(f"{where}: evaluate.{name}: {error}") from error

    unknown = unknown_names(evaluate)
    if unknown:
        raise ValueError(f"{where}: unknown evaluations: {', '.join(unknown)}")

    root = (root or Path.cwd()).resolve()
    for name, options in evaluate.items():
        validate = VALIDATORS.get(name)
        if validate is None:
            continue
        try:
            validate(options, root, workspace)
        except ValueError as error:
            raise ValueError(f"{where}: evaluate.{name}: {error}") from error
    return evaluate


def blank_document(
    experiment_id: str, question: str, workspace: str, prompt: str = "task.md"
) -> dict[str, Any]:
    """The smallest description that still runs: one candidate, one stage.

    A new experiment starts from something valid rather than from an empty page,
    so the first thing a person sees is a working shape to change.
    """
    return {
        "id": experiment_id,
        "question": question,
        "workspace": workspace,
        "task": experiment_id,
        "candidates": [
            {
                "id": "single",
                "stages": [
                    {
                        "role": "SOLVER",
                        "model": "",
                        "prompt": f"experiments/{experiment_id}/{prompt}",
                        "allow_edit": [],
                    }
                ],
            }
        ],
    }


def leading_comment(text: str) -> str:
    """Return the comment block a description opens with, blank line included.

    An editor that dropped it would silently discard the note explaining what the
    experiment reproduces and where its reference numbers live.
    """
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            lines.append(line)
            continue
        if not line.strip() and lines:
            lines.append("")
            continue
        break
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def relative_to(path: Path, root: Path) -> str:
    """Inside the repository a path stays relative; outside it stays absolute."""
    resolved = Path(path).resolve()
    if resolved.is_relative_to(root):
        return str(resolved.relative_to(root))
    return str(resolved)


def reference_value(reference: dict[str, str]) -> Any:
    """Write the short form back as short, the versioned form as a mapping."""
    if reference.get("version", "1") == "1":
        return reference["id"]
    return dict(reference)


def reference_text(value: Any) -> str:
    """Render a task or case reference for a form field: ``name`` or ``name@2``."""
    if isinstance(value, dict):
        version = str(value.get("version", "1"))
        name = str(value.get("id", ""))
        return name if version == "1" else f"{name}@{version}"
    return str(value)


def reference_field(text: str) -> Any:
    """Read back what ``reference_text`` wrote."""
    if "@" in text:
        name, _, version = text.rpartition("@")
        return {"id": name, "version": version}
    return text


def folded(value: str, indent: str = "  ") -> list[str]:
    """A folded block scalar, wrapped where a hand-written file would wrap."""
    return [
        indent + line
        for line in textwrap.wrap(
            " ".join(value.split()), width=LINE_WIDTH - len(indent)
        )
    ]


def option_value(value: Any) -> str:
    """Write an option back as YAML, in the flow form the rest of the file uses.

    A list matters here: a suite command is an explicit argument list and must
    read back as one, the way ``allow_edit`` already does.
    """
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def dump_experiment(
    experiment: Experiment, root: Path | None = None, header: str = ""
) -> str:
    """Serialise a description in the style the hand-written files already use.

    Written by hand rather than with ``yaml.dump`` because the field order, the
    folded question and the leading comment all carry meaning that a generic
    dumper would rearrange, and because pulling in a round-tripping YAML library
    for eight fields would cost more than it returns.
    """
    root = (root or Path.cwd()).resolve()
    lines: list[str] = []
    if header:
        lines.extend(header.splitlines())
        lines.append("")

    lines.append(f"id: {experiment.id}")
    lines.append("question: >-")
    lines.extend(folded(experiment.question))
    lines.append("")
    lines.append(f"workspace: {relative_to(experiment.workspace, root)}")
    lines.append(f"task: {reference_value(experiment.task)}")
    lines.append(f"case: {reference_value(experiment.case)}")
    if experiment.repetitions != 1:
        lines.append(f"repetitions: {experiment.repetitions}")

    if experiment.evaluate:
        lines.append("")
        lines.append("evaluate:")
        for name, options in sorted(experiment.evaluate.items()):
            # The one-key form is written back as the shorthand it came from.
            if set(options) == {"document"}:
                lines.append(f"  {name}: {options['document']}")
                continue
            lines.append(f"  {name}:")
            for key, value in options.items():
                lines.append(f"    {key}: {option_value(value)}")

    lines.append("")
    lines.append("candidates:")
    for candidate in experiment.candidates:
        lines.append(f"  - id: {candidate.id}")
        lines.append("    stages:")
        for stage in candidate.stages:
            allow = ", ".join(stage.allow_edit)
            lines.append(f"      - role: {stage.role}")
            lines.append(f"        model: {stage.model}")
            lines.append(f"        prompt: {relative_to(stage.prompt, root)}")
            lines.append(f"        allow_edit: [{allow}]")
            if stage.provider != "openrouter":
                lines.append(f"        provider: {stage.provider}")
            if stage.base_url:
                lines.append(f"        base_url: {stage.base_url}")
            if stage.api_key_env:
                lines.append(f"        api_key_env: {stage.api_key_env}")
        lines.append("")

    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def indexed(fields: dict[str, list[str]], prefix: str) -> list[str]:
    """Sorted numeric indices present under ``prefix``, e.g. ``candidate.0.id``."""
    found: set[int] = set()
    for key in fields:
        if not key.startswith(prefix):
            continue
        head = key[len(prefix):].split(".", 1)[0]
        if head.isdigit():
            found.add(int(head))
    return [str(item) for item in sorted(found)]


def one(fields: dict[str, list[str]], key: str, default: str = "") -> str:
    values = fields.get(key) or [default]
    return values[0].strip()


def experiment_document(fields: dict[str, list[str]]) -> dict[str, Any]:
    """Assemble a description from the flat form fields the shell posts.

    The shell parses its own urlencoded body, so the fields arrive as the plain
    ``{name: [value]}`` mapping ``urllib.parse.parse_qs`` produces.
    """
    candidates: list[dict[str, Any]] = []
    for index in indexed(fields, "candidate."):
        stages: list[dict[str, Any]] = []
        for position in indexed(fields, f"candidate.{index}.stage."):
            stem = f"candidate.{index}.stage.{position}"
            stage: dict[str, Any] = {
                "role": one(fields, f"{stem}.role", "OTHER").upper(),
                "model": one(fields, f"{stem}.model"),
                "prompt": one(fields, f"{stem}.prompt"),
                # One input per path, but a single comma-separated field is still
                # accepted: both shapes arrive as values of the same name.
                "allow_edit": [
                    item.strip()
                    for value in fields.get(f"{stem}.allow_edit", [])
                    for item in value.split(",")
                    if item.strip()
                ],
            }
            for optional in ("provider", "base_url", "api_key_env"):
                value = one(fields, f"{stem}.{optional}")
                if value:
                    stage[optional] = value
            stages.append(stage)
        candidates.append({"id": one(fields, f"candidate.{index}.id"), "stages": stages})

    document: dict[str, Any] = {
        "id": one(fields, "id"),
        "question": one(fields, "question"),
        "workspace": one(fields, "workspace"),
        "candidates": candidates,
    }
    # An empty reference field means "use the default" — the experiment id for a
    # task, the workspace name for a case. Writing it out as an empty value would
    # produce a description that no longer reads back.
    for name in ("task", "case"):
        text = one(fields, name)
        if text:
            document[name] = reference_field(text)
    repetitions = one(fields, "repetitions", "1")
    document["repetitions"] = int(repetitions) if repetitions.isdigit() else repetitions

    document["evaluate"] = evaluate_from_fields(fields)
    if not document["evaluate"]:
        del document["evaluate"]
    return document


def evaluate_from_fields(fields: dict[str, list[str]]) -> dict[str, Any]:
    """Read the registry back from form fields.

    Both shapes the form can post are accepted: ``evaluate.citations`` naming a
    document, and ``evaluate.claims.model`` tuning an evaluator. An option left
    blank is dropped, and an evaluation whose options all went blank disappears —
    that is how the form says "do not measure this".
    """
    evaluate: dict[str, Any] = {}
    for key in fields:
        if not key.startswith("evaluate."):
            continue
        rest = key[len("evaluate.") :]
        name, _, option = rest.partition(".")
        value = one(fields, key)
        if not name or not value:
            continue
        options = evaluate.setdefault(name, {})
        options[option or "document"] = value
    return {name: options for name, options in evaluate.items() if options}

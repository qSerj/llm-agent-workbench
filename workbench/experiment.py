"""Read a short experiment description and turn it into runnable candidates.

The description is deliberately small: a human question, the workspace under
test, and the candidates being compared. A field is added when a real run needed
it, not because a hypothetical scenario might.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workbench.chain import StageSpec

STAGE_ROLES = {"SOLVER", "REVIEWER", "FIXER", "OTHER"}


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
    evaluate: dict[str, str] = field(default_factory=dict)

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
    """Accept either ``name`` or ``{id: name, version: "2"}``."""
    if isinstance(value, str):
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
    root = (root or Path.cwd()).resolve()
    document = read_yaml(path)
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
        evaluate={
            str(key): str(value)
            for key, value in (document.get("evaluate") or {}).items()
        },
    )

"""Build execution envelope v1 records from legacy OpenCode run bundles."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "execution-envelope-v1.schema.json"
LEGACY_OUTPUTS = {
    1: "docs/01-interleavers.md",
    2: "docs/02-apply-behavior.md",
    3: "docs/03-public-api.md",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_artifact(
    artifact_id: str,
    role: str,
    path: Path,
    bundle_root: Path,
    media_type: str,
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "role": role,
        "content_kind": "FILE",
        "media_type": media_type,
        "byte_size": path.stat().st_size,
        "sha256": sha256(path),
        "digest_method": "sha256-file-bytes",
        "location": {"path": path.relative_to(bundle_root).as_posix()},
    }


def directory_artifact(
    artifact_id: str,
    role: str,
    path: Path,
    bundle_root: Path,
    media_type: str,
    excluded_directory_names: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    digest, byte_size = directory_digest(path, excluded_directory_names)
    return {
        "id": artifact_id,
        "role": role,
        "content_kind": "DIRECTORY",
        "media_type": media_type,
        "byte_size": byte_size,
        "sha256": digest,
        "digest_method": "sha256-tree-manifest-v1",
        "location": {"path": path.relative_to(bundle_root).as_posix()},
        "exclusions": sorted(excluded_directory_names),
    }


def directory_digest(
    path: Path, excluded_directory_names: frozenset[str] = frozenset()
) -> tuple[str, int]:
    files = sorted(
        item
        for item in path.rglob("*")
        if item.is_file()
        and not excluded_directory_names.intersection(item.relative_to(path).parts)
    )
    manifest_lines = []
    byte_size = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        item_size = item.stat().st_size
        manifest_lines.append(f"{sha256(item)}  {item_size}  {relative}\n")
        byte_size += item_size
    return hashlib.sha256("".join(manifest_lines).encode("utf-8")).hexdigest(), byte_size


def artifact_files(path: Path, excluded_directory_names: frozenset[str]) -> list[Path]:
    return sorted(
        item
        for item in path.rglob("*")
        if item.is_file()
        and not excluded_directory_names.intersection(item.relative_to(path).parts)
    )


def verify_artifacts(envelope: dict[str, Any], bundle_root: Path) -> None:
    """Verify local artifact paths, sizes, and hashes before projection."""
    bundle_root = bundle_root.resolve()
    for item in envelope["artifacts"]:
        location = item["location"]
        if "path" not in location:
            continue
        candidate = (bundle_root / location["path"]).resolve()
        if not candidate.is_relative_to(bundle_root):
            raise ValueError(f"artifact path escapes bundle root: {location['path']}")
        if item["content_kind"] == "FILE":
            if not candidate.is_file():
                raise ValueError(f"artifact file is missing: {location['path']}")
            actual_digest, actual_size = sha256(candidate), candidate.stat().st_size
        else:
            if not candidate.is_dir():
                raise ValueError(f"artifact directory is missing: {location['path']}")
            exclusions = frozenset(item.get("exclusions", []))
            actual_digest, actual_size = directory_digest(candidate, exclusions)
        if actual_size != item["byte_size"] or actual_digest != item["sha256"]:
            raise ValueError(f"artifact content mismatch: {item['id']}")


def observation(name: str, value: Any, unit: str, method: str) -> dict[str, Any]:
    return {"name": name, "value": value, "unit": unit, "method": method}


def _lifecycle(timestamp: str, wall_seconds: float, status: str) -> dict[str, Any]:
    # Legacy timestamps have no UTC offset. Preserve that limitation explicitly
    # instead of assigning the importing machine's current timezone.
    started = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
    finished = started + timedelta(seconds=wall_seconds)
    return {
        "status": status,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="milliseconds"),
        "timestamp_basis": "legacy-local-time-offset-unknown",
    }


def _code_evaluation(grade: dict[str, Any]) -> dict[str, Any]:
    checks = [
        {
            "id": item["name"],
            "outcome": "PASS" if item["ok"] else "FAIL",
            "value": item["points"],
            "maximum": item["max_points"],
        }
        for item in grade["checks"]
    ]
    return {
        "id": "deterministic-grader",
        "subject": {"kind": "EXECUTION", "id": "self"},
        "evaluator": {"source": "CODE", "identity": "grade.py"},
        "policy": {"id": f"legacy-task-{grade['task']}-grader", "version": "r4.2"},
        "result": {
            "verdict": "PASS" if grade["score"] == grade["max_score"] else "FAIL",
            "checks": checks,
        },
        "rationale": f"Deterministic score {grade['score']}/{grade['max_score']}.",
        "evidence_artifact_ids": ["grader-output"],
    }


def build_legacy_opencode_envelope(
    task_directory: Path,
    human_evaluation_path: Path | None = None,
) -> dict[str, Any]:
    """Convert one task directory from the r4.2 runner into envelope v1."""
    task_directory = task_directory.resolve()
    run_directory = task_directory.parent
    if not task_directory.name.startswith("task"):
        raise ValueError("task directory name must look like task01")

    metadata = read_json(run_directory / "metadata.json")
    exit_info = read_json(task_directory / "exit.json")
    grade = read_json(task_directory / "grade.json")
    task_number = int(task_directory.name.removeprefix("task"))
    workspace = task_directory / "workspace"
    try:
        output_path = workspace / LEGACY_OUTPUTS[task_number]
    except KeyError as error:
        raise ValueError(f"unsupported legacy task number: {task_number}") from error

    bundle_root = run_directory
    prompt_path = task_directory / "prompt.md"
    trace_path = task_directory / "opencode.jsonl"
    grade_path = task_directory / "grade.json"
    effective_model = (task_directory / "effective_model.txt").read_text(
        encoding="utf-8"
    ).strip()

    output_exists = output_path.is_file()
    if exit_info["returncode"] == 0 and output_exists:
        status = "SUCCEEDED"
    elif output_exists and output_path.stat().st_size > 0:
        status = "PARTIAL"
    else:
        status = "FAILED"
    artifacts = [
        file_artifact("task-prompt", "INPUT", prompt_path, bundle_root, "text/markdown"),
        directory_artifact(
            "source-tree",
            "INPUT",
            workspace / "src",
            bundle_root,
            "application/vnd.llm-agent-workbench.source-tree",
            frozenset({"bin", "obj"}),
        ),
        # The historical runner merged stdout and stderr, so this is not guaranteed
        # to be valid NDJSON even though its filename ends in .jsonl.
        file_artifact("raw-opencode-stream", "LOG", trace_path, bundle_root, "text/plain"),
        file_artifact("grader-output", "EVIDENCE", grade_path, bundle_root, "application/json"),
    ]
    if output_exists:
        artifacts.insert(
            2,
            file_artifact(
                "generated-document", "OUTPUT", output_path, bundle_root, "text/markdown"
            ),
        )

    observations = [
        observation("wall_time", exit_info["wall_seconds"], "s", "monotonic-clock"),
        observation("tool_calls", exit_info["tool_calls"], "{call}", "opencode-event-count"),
        observation(
            "failed_tool_calls",
            exit_info["failed_tool_calls"],
            "{call}",
            "opencode-event-count",
        ),
    ]
    tokens = exit_info.get("summed_step_tokens")
    if tokens is not None:
        for token_kind in ("input", "output", "reasoning", "total"):
            observations.append(
                observation(
                    f"tokens.{token_kind}",
                    tokens[token_kind],
                    "{token}",
                    "sum-of-opencode-step-finish-events",
                )
            )
    if exit_info.get("total_reported_cost_usd") is not None:
        observations.append(
            observation(
                "api_cost",
                exit_info["total_reported_cost_usd"],
                "USD",
                "provider-reported-opencode-step-cost-sum",
            )
        )
    if exit_info.get("estimated_kwh") is not None:
        observations.append(
            observation(
                "local_energy",
                exit_info["estimated_kwh"],
                "kWh",
                "wall-time-times-user-supplied-average-power",
            )
        )

    evaluations = [_code_evaluation(grade)]
    if human_evaluation_path is not None:
        if not output_exists:
            raise ValueError("human evaluation cannot attach: output artifact is missing")
        human_evaluation = read_json(human_evaluation_path)
        expected_hash = human_evaluation.pop("subject_sha256")
        if expected_hash != sha256(output_path):
            raise ValueError("human evaluation subject hash does not match output artifact")
        evaluations.append(human_evaluation)

    prompt_hash = sha256(prompt_path)
    source_artifact = next(item for item in artifacts if item["id"] == "source-tree")
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_id": f"legacy-opencode:{run_directory.name}:{task_directory.name}",
        "task": {
            "id": f"repository-documentation-{task_number:02d}",
            "version": f"sha256:{prompt_hash}",
        },
        "case": {
            "id": "interleaver-fixture",
            "version": f"sha256:{source_artifact['sha256']}",
            "parameters": {"legacy_fixture_version": "r4.2"},
        },
        "candidate": {
            "id": "legacy-opencode-agent",
            "version": metadata["runner_version"],
            "parameters": {
                "provider": metadata["provider"],
                "model": metadata["model"],
                "effective_model": effective_model,
                "context_tokens": metadata["context"],
            },
        },
        "repetition": 1,
        "lifecycle": _lifecycle(metadata["timestamp"], exit_info["wall_seconds"], status),
        "executor": {
            "implementation": "run_agent.py",
            "version": metadata["runner_version"],
            "exit_code": exit_info["returncode"],
        },
        "artifacts": artifacts,
        "observations": observations,
        "evaluations": evaluations,
        "correlations": [],
    }


def validate_envelope(envelope: dict[str, Any]) -> None:
    """Validate using the standard JSON Schema implementation."""
    try:
        import jsonschema
    except ImportError as error:
        raise RuntimeError(
            "validation requires jsonschema; install requirements-envelope.txt"
        ) from error
    schema = read_json(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)
    errors = sorted(validator.iter_errors(envelope), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(
            f"/{'/'.join(map(str, error.path))}: {error.message}" for error in errors
        )
        raise ValueError(f"invalid execution envelope: {details}")

    artifact_ids = [item["id"] for item in envelope["artifacts"]]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("invalid execution envelope: artifact IDs must be unique")
    artifact_id_set = set(artifact_ids)
    evaluation_ids = [item["id"] for item in envelope["evaluations"]]
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError("invalid execution envelope: evaluation IDs must be unique")

    for evaluation in envelope["evaluations"]:
        subject = evaluation["subject"]
        if subject["kind"] == "ARTIFACT" and subject["id"] not in artifact_id_set:
            raise ValueError(
                f"invalid execution envelope: unknown subject artifact {subject['id']}"
            )
        unknown_evidence = set(evaluation["evidence_artifact_ids"]) - artifact_id_set
        if unknown_evidence:
            raise ValueError(
                "invalid execution envelope: unknown evidence artifacts "
                + ", ".join(sorted(unknown_evidence))
            )
        for dimension in evaluation["result"].get("dimensions", []):
            scale = dimension["scale"]
            if scale["minimum"] > scale["maximum"]:
                raise ValueError(
                    f"invalid execution envelope: inverted scale for {dimension['id']}"
                )
            if not scale["minimum"] <= dimension["value"] <= scale["maximum"]:
                raise ValueError(
                    f"invalid execution envelope: value outside scale for {dimension['id']}"
                )

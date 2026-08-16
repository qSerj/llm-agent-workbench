"""Validate execution cards and verify their local artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "execution-envelope-v1.schema.json"


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

    stages = envelope.get("stages", [])
    stage_ids = [item["id"] for item in stages]
    if len(stage_ids) != len(set(stage_ids)):
        raise ValueError("invalid execution envelope: stage IDs must be unique")
    stage_id_set = set(stage_ids)
    dependencies = {item["id"]: set(item["depends_on"]) for item in stages}
    for stage in stages:
        unknown_dependencies = set(stage["depends_on"]) - stage_id_set
        if unknown_dependencies:
            raise ValueError(
                "invalid execution envelope: unknown stage dependencies "
                + ", ".join(sorted(unknown_dependencies))
            )
        if stage["id"] in stage["depends_on"]:
            raise ValueError(
                f"invalid execution envelope: stage depends on itself: {stage['id']}"
            )
        unknown_artifacts = (
            set(stage["input_artifact_ids"] + stage["output_artifact_ids"])
            - artifact_id_set
        )
        if unknown_artifacts:
            raise ValueError(
                "invalid execution envelope: unknown stage artifacts "
                + ", ".join(sorted(unknown_artifacts))
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visiting:
            raise ValueError("invalid execution envelope: stage dependency cycle")
        if stage_id in visited:
            return
        visiting.add(stage_id)
        for dependency in dependencies[stage_id]:
            visit(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)

    for stage_id in stage_ids:
        visit(stage_id)

    for item in envelope["observations"]:
        if "stage_id" in item and item["stage_id"] not in stage_id_set:
            raise ValueError(
                f"invalid execution envelope: unknown observation stage {item['stage_id']}"
            )

    for evaluation in envelope["evaluations"]:
        subject = evaluation["subject"]
        if subject["kind"] == "ARTIFACT" and subject["id"] not in artifact_id_set:
            raise ValueError(
                f"invalid execution envelope: unknown subject artifact {subject['id']}"
            )
        if subject["kind"] == "STAGE" and subject["id"] not in stage_id_set:
            raise ValueError(
                f"invalid execution envelope: unknown subject stage {subject['id']}"
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

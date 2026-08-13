"""Project a validated execution envelope into MLflow."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from workbench.envelope import artifact_files, validate_envelope, verify_artifacts


def project_to_mlflow(
    envelope: dict[str, Any],
    bundle_root: Path,
    tracking_uri: str,
    experiment_name: str,
) -> tuple[str, dict[str, Any]]:
    try:
        import mlflow
    except ImportError as error:
        raise RuntimeError("MLflow projection requires the optional research environment") from error

    validate_envelope(envelope)
    verify_artifacts(envelope, bundle_root)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    tags = {
        "workbench.schema_version": envelope["schema_version"],
        "workbench.execution_id": envelope["execution_id"],
        "workbench.task.id": envelope["task"]["id"],
        "workbench.task.version": envelope["task"]["version"],
        "workbench.case.id": envelope["case"]["id"],
        "workbench.case.version": envelope["case"]["version"],
        "workbench.candidate.id": envelope["candidate"]["id"],
        "workbench.candidate.version": envelope["candidate"]["version"],
        "workbench.status": envelope["lifecycle"]["status"],
    }
    run_name = f"{envelope['candidate']['id']}__{envelope['case']['id']}__r{envelope['repetition']}"
    with mlflow.start_run(run_name=run_name, tags=tags) as run:
        mlflow.log_params(
            {
                "task": f"{envelope['task']['id']}@{envelope['task']['version']}",
                "case": f"{envelope['case']['id']}@{envelope['case']['version']}",
                "candidate": f"{envelope['candidate']['id']}@{envelope['candidate']['version']}",
                "repetition": envelope["repetition"],
                "exit_code": envelope["executor"]["exit_code"],
            }
        )
        for item in envelope["observations"]:
            value = item["value"]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                mlflow.log_metric(item["name"], value)

        for evaluation in envelope["evaluations"]:
            evaluation_id = evaluation["id"]
            mlflow.set_tags(
                {
                    f"evaluation.{evaluation_id}.source": evaluation["evaluator"]["source"],
                    f"evaluation.{evaluation_id}.verdict": evaluation["result"]["verdict"],
                    f"evaluation.{evaluation_id}.policy": (
                        f"{evaluation['policy']['id']}@{evaluation['policy']['version']}"
                    ),
                }
            )
            for check in evaluation["result"].get("checks", []):
                mlflow.log_metric(
                    f"evaluation.{evaluation_id}.check.{check['id']}",
                    1 if check["outcome"] == "PASS" else 0,
                )
            for dimension in evaluation["result"].get("dimensions", []):
                mlflow.log_metric(
                    f"evaluation.{evaluation_id}.dimension.{dimension['id']}",
                    dimension["value"],
                )

        for item in envelope["artifacts"]:
            location = item["location"]
            if "path" not in location:
                continue
            source = (bundle_root / location["path"]).resolve()
            destination = f"artifacts/{item['id']}"
            if source.is_dir():
                exclusions = frozenset(item.get("exclusions", []))
                for file_path in artifact_files(source, exclusions):
                    relative_parent = file_path.relative_to(source).parent.as_posix()
                    artifact_path = destination
                    if relative_parent != ".":
                        artifact_path = f"{destination}/{relative_parent}"
                    mlflow.log_artifact(str(file_path), artifact_path=artifact_path)
            else:
                mlflow.log_artifact(str(source), artifact_path=destination)

        correlated = json.loads(json.dumps(envelope))
        correlated["correlations"].append(
            {"system": "mlflow", "kind": "run_id", "value": run.info.run_id}
        )
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "execution-envelope.json"
            record.write_text(json.dumps(correlated, indent=2) + "\n", encoding="utf-8")
            mlflow.log_artifact(str(record), artifact_path="workbench")
        return run.info.run_id, correlated

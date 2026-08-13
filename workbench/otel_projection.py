"""Project an execution envelope into OpenTelemetry spans."""

from __future__ import annotations

from typing import Any

from workbench.envelope import validate_envelope


def project_to_otel(envelope: dict[str, Any], tracer: Any) -> tuple[str, str]:
    """Emit one execution span and return lowercase OTel trace/span IDs."""
    validate_envelope(envelope)
    attributes = {
        "workbench.schema.version": envelope["schema_version"],
        "workbench.execution.id": envelope["execution_id"],
        "workbench.task.id": envelope["task"]["id"],
        "workbench.task.version": envelope["task"]["version"],
        "workbench.case.id": envelope["case"]["id"],
        "workbench.case.version": envelope["case"]["version"],
        "workbench.candidate.id": envelope["candidate"]["id"],
        "workbench.candidate.version": envelope["candidate"]["version"],
        "workbench.execution.status": envelope["lifecycle"]["status"],
        "workbench.repetition": envelope["repetition"],
        "workbench.execution.started_at": envelope["lifecycle"]["started_at"],
        "workbench.execution.finished_at": envelope["lifecycle"]["finished_at"],
        "workbench.execution.timestamp_basis": envelope["lifecycle"]["timestamp_basis"],
    }
    with tracer.start_as_current_span("task.execute", attributes=attributes) as span:
        for stage in envelope.get("stages", []):
            with tracer.start_as_current_span(
                f"stage.{stage['role'].lower()}",
                attributes={
                    "workbench.stage.id": stage["id"],
                    "workbench.stage.role": stage["role"],
                    "workbench.stage.execution_id": stage["execution_id"],
                    "workbench.stage.depends_on": stage["depends_on"],
                    "workbench.stage.input_artifact_ids": stage["input_artifact_ids"],
                    "workbench.stage.output_artifact_ids": stage["output_artifact_ids"],
                },
            ):
                pass
        for item in envelope["observations"]:
            event_attributes = {
                "workbench.observation.name": item["name"],
                "workbench.observation.unit": item["unit"],
                "workbench.observation.method": item["method"],
            }
            value = item["value"]
            if value is not None:
                event_attributes["workbench.observation.value"] = value
            if "stage_id" in item:
                event_attributes["workbench.observation.stage_id"] = item["stage_id"]
            span.add_event("workbench.observation", event_attributes)

        for item in envelope["artifacts"]:
            span.add_event(
                "workbench.artifact",
                {
                    "workbench.artifact.id": item["id"],
                    "workbench.artifact.role": item["role"],
                    "workbench.artifact.media_type": item["media_type"],
                    "workbench.artifact.sha256": item["sha256"],
                    "workbench.artifact.byte_size": item["byte_size"],
                },
            )

        for item in envelope["evaluations"]:
            span.add_event(
                "workbench.evaluation.result",
                {
                    "workbench.evaluation.id": item["id"],
                    "workbench.evaluation.source": item["evaluator"]["source"],
                    "workbench.evaluation.subject.kind": item["subject"]["kind"],
                    "workbench.evaluation.subject.id": item["subject"]["id"],
                    "workbench.evaluation.verdict": item["result"]["verdict"],
                    "workbench.evaluation.policy.id": item["policy"]["id"],
                    "workbench.evaluation.policy.version": item["policy"]["version"],
                },
            )

        if envelope["lifecycle"]["status"] != "SUCCEEDED":
            from opentelemetry.trace import Status, StatusCode

            span.set_status(
                Status(
                    StatusCode.ERROR,
                    f"execution ended as {envelope['lifecycle']['status']}",
                )
            )
        context = span.get_span_context()
        return f"{context.trace_id:032x}", f"{context.span_id:016x}"

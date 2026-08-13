# ADR 0003: Portable Execution Envelope and Projections

Status: accepted, 2026-08-12.

## Context

The minimal composition experiments imported both complete and partial
OpenCode runs, exported a real OTLP protobuf trace, and evaluated two ordinary
programs that consumed and produced binary audio. MLflow handled experiment
records and arbitrary artifacts; OpenTelemetry represented execution activity.
Neither standard should redefine task intent, artifact semantics, or the
subject of an evaluation.

Failure exposed a second boundary: a nominal JSONL file may contain merged
stderr. Derived indexes can be repaired, but the original execution bundle
must not be replaced by a lossy normalization.

## Decision

Own only a small, versioned execution envelope. It identifies the task, case,
candidate, repetition, execution status, artifacts, observations, evaluations,
and external correlations. Artifacts are referenced by role, media type, byte
size, content hash, and location; their contents are not assumed to be text.

Keep raw executor output and artifacts authoritative. Import them into MLflow
as the canonical queryable experiment record. Export activity as OpenTelemetry
OTLP using GenAI and OpenInference conventions where applicable. Preserve
provider-specific data with namespaced attributes or raw artifacts rather than
inventing competing generic span semantics.

Evaluation is separate from telemetry. It names its subject—execution, output
artifact, claim, or trajectory—and records evaluator source (`CODE`,
`LLM_JUDGE`, or `HUMAN`), rubric/policy version, value, rationale, and evidence
references. A failed or partial attempt is still an execution and can be
evaluated.

## Consequences

The project needs adapters and validation for the envelope, not its own trace
backend, artifact store, evaluator framework, or UI. MLflow-specific run and
trace IDs and OTel trace/span IDs are correlations, not domain primary keys.

An adapter may create a coarse trace when a backend requires trace-attached
human feedback. If this becomes awkward across several modalities or tools,
record the repeated mismatch before extending the owned model. The concrete
serialization was deliberately deferred until human review and another
modality exercised it. Both gates are now complete; JSON serialization and
evaluation semantics are specified in
[ADR 0004](0004-envelope-v1-serialization-and-evaluation.md).

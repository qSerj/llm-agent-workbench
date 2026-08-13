# ADR 0004: Envelope v1 Serialization and Evaluation Semantics

Status: accepted for the first reproducible adapter, 2026-08-13.

## Context

The composition experiments exercised successful, partial, and failed agent
executions, OTLP export, and binary artifacts. The first genuine human review
then gave a generated report `correctness = 1/2` and `PASS`: the result was
useful overall but contained a fabricated example. It also showed that neither
a universal 0–2 nor a universal 0–10 scale fits tasks of different complexity.

The project now needs a concrete interchange format without turning the
interchange model into a database, workflow engine, or universal rubric.

## Decision

Version 1 of the project-owned execution envelope will be a UTF-8 JSON document
validated by a committed JSON Schema using JSON Schema Draft 2020-12. JSON is
the machine interchange format because runner output, MLflow adapters, and
OpenTelemetry correlation data already cross JSON-shaped boundaries. Friendly
task authoring formats may be added later and compiled into this envelope;
they are not part of v1.

The envelope will contain these required top-level groups:

- `schema_version` and a project-generated `execution_id`;
- versioned references for `task`, `case`, and `candidate`, plus `repetition`;
- lifecycle `status`, timestamps, and executor exit information;
- input and output `artifacts` with role, media type, byte size, SHA-256, and a
  relative location or external URI;
- typed `observations` with value, unit, method, and optional uncertainty;
- `evaluations` naming their subject, evaluator source, policy version,
  result, rationale, and evidence references;
- external `correlations`, including MLflow run/trace IDs and OTel trace/span
  IDs when available.

Unknown measurements are omitted or explicitly `null`; zero never represents
unknown. Raw logs and artifacts remain authoritative and are referenced rather
than embedded by default. Paths inside a portable bundle must be relative and
must not escape its root. Content hashes are required for evaluated output
artifacts.

An evaluation result is policy-defined, not a universal number. It may contain:

- explicit checks with stable identifiers and pass/fail outcomes;
- a separate overall `PASS`, `FAIL`, or `UNDETERMINED` verdict;
- optional dimensions whose scale, direction, and anchored meanings are
  declared by the referenced evaluation policy.

No generic total is inferred across dimensions, and no verdict is inferred
from a score unless that policy declares the rule. `CODE`, `HUMAN`, and
`LLM_JUDGE` evaluations remain distinguishable. Model review is not human
review and must record provider, model, prompt/policy version, and usage.

## Consequences

The first implementation can validate and import a complete bundle without
deciding how every future task is authored. MLflow remains the canonical
queryable record and artifact store; OTLP remains a telemetry projection.
Their identifiers do not replace the envelope's identity.

The v1 schema should be tested first against the existing successful run, the
partial failure, and both audio candidates. A later
`solver → reviewer → fixer` experiment will test whether evaluations and
revision lineage are sufficient before adding pipeline-specific concepts.

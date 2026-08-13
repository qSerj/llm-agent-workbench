# Execution Envelope v1

The execution envelope is the small project-owned interchange record between
an arbitrary executor and integrations such as MLflow and OpenTelemetry. It is
not a workflow definition, trace format, or artifact store.

The schema is
[`schemas/execution-envelope-v1.schema.json`](../schemas/execution-envelope-v1.schema.json).
Validation uses the standard `jsonschema` package:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-envelope.txt
.venv/bin/python tools/legacy_opencode_to_envelope.py \
  agent_runs/<run>/task01 \
  --output /tmp/execution-envelope.json
```

Add `--human-evaluation evaluations/legacy-task01-qserj-2026-08-13.json`
when converting the matching historical execution. The adapter verifies the
reviewed output's SHA-256 before attaching the assessment.

## Semantics

`task`, `case`, and `candidate` are versioned identities. The legacy adapter
content-addresses the task prompt and filtered source tree rather than trusting
a mutable label. `artifacts` may be
files or directory trees and remain external to the JSON. A directory digest
is calculated over a deterministic manifest; the legacy source-tree adapter
excludes `bin` and `obj`. `observations` always state a unit and measurement
method. Unknown values are omitted or `null`, never silently converted to zero.

Evaluations name their subject and retain their source as `CODE`, `HUMAN`, or
`LLM_JUDGE`. Checks, optional anchored dimensions, and the overall verdict are
independent. No universal score or implicit verdict threshold exists.

## Optional Projections

After activating the transferred research environment, import a validated
record and its verified local artifacts into MLflow:

```bash
python tools/envelope_to_mlflow.py /tmp/execution-envelope.json \
  --bundle-root agent_runs/<run> \
  --tracking-uri sqlite:////tmp/workbench-mlflow.db
```

Export the execution projection to any OTLP/HTTP receiver:

```bash
python tools/envelope_to_otlp.py /tmp/execution-envelope.json \
  --endpoint http://127.0.0.1:4318/v1/traces
```

MLflow run IDs and OTel trace/span IDs are correlations. They do not replace
the workbench execution identity or make either backend authoritative for task
semantics.

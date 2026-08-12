# ADR 0002: Initial Tool Composition

Status: accepted for the minimal composition experiment, 2026-08-12. This is
not a final platform architecture.

## Context

The domain-neutral scenario compared two local candidate strategies over two
evidence-report cases and two repetitions. A second scenario ran the historical
OpenCode benchmark through LM Studio/GPT-OSS and imported its complete external
execution into MLflow without changing the runner. MLflow, Inspect AI, and
Promptfoo represented the experiment matrix, but each emphasized a different
boundary. Opik's exact Compose profile was inspected without pulling or
starting the full stack.

## Decision

- Use **MLflow** as the canonical experiment, artifact, trace, assessment, and
  system-metric record for the next experiment. Write once to MLflow, then
  export; do not dual-write the same canonical data to several products.
- Use **Inspect AI** when a candidate is naturally expressed as an Inspect task
  or requires its epochs, limits, sandboxing, or rich transcripts. External
  candidates such as OpenCode remain black boxes and import directly to MLflow.
- Use **Promptfoo** only where its prompt/provider/test matrix and CI assertions
  are the natural fit. Do not make its text-result cell the universal artifact
  abstraction.
- Keep **Opik** optional. Its three application images total roughly 1.04 GB of
  compressed layers for amd64 before MySQL, ClickHouse, Redis, MinIO, ZooKeeper,
  and helper images. The full Compose profile has eleven services, usage
  reporting enabled by default, and a privileged Python backend.
- Export execution telemetry with **OpenTelemetry/OpenInference** conventions.
- Treat **CodeCarbon** as a labelled estimator unless RAPL/NVML or an external
  meter provides real readings.

Do not select Prefect, Dagster, Hamilton, or another workflow runtime yet. The
simple Python and Inspect execution paths must first demonstrate a scheduling,
recovery, or lineage gap that warrants one.

## Evidence and Remaining Risks

The legacy adapter preserved raw OpenCode JSONL, workspace, grader output,
metrics, and stable task/case/candidate identities. It correlated the external
run with an MLflow trace using source timestamps and added a new assessment
without repeating inference. It also exposed two domain-level issues: a perfect
grader score masked an unsupported claim, and `git.diff` omitted an untracked
output that remained available in the workspace artifact.

Follow-up experiments successfully imported a partial execution, exported the
legacy trace as real OTLP/HTTP protobuf, and stored and evaluated binary audio
artifacts produced by ordinary programs. See the
[composition results](../research/composition-results-2026-08-12.md) and
[ADR 0003](0003-portable-execution-envelope.md). Actual human review remains
open. If artifact-first execution or claim-level evidence repeatedly fights
the selected tools, document that concrete gap before expanding the small
project-owned envelope.

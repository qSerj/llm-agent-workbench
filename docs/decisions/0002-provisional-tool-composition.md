# ADR 0002: Provisional Tool Composition

Status: proposed after the first domain-neutral bake-off, 2026-08-12.

## Context

The first hands-on scenario compared two local candidate strategies over two
evidence-report cases and two repetitions. MLflow, Inspect AI, and Promptfoo all
represented the matrix, but each emphasized a different boundary. Opik's exact
Compose profile was also inspected without pulling or starting the full stack.

## Provisional Direction

- Evaluate **MLflow** as the canonical experiment, artifact, trace, assessment,
  and system-metric record. Write once to MLflow, then export; do not dual-write
  the same canonical data to several products.
- Evaluate **Inspect AI** as the primary harness when candidates are agents or
  multi-step solvers and require epochs, limits, sandboxing, or rich transcripts.
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

## Validation Required

This proposal is not accepted until the existing OpenCode benchmark is imported
and one real provider-backed run is executed. That second scenario must test:

- large directory artifacts and failed/partial executions;
- preservation of raw OpenCode JSONL, workspace, diff, and grader output;
- candidate and task version identity independent of MLflow naming;
- correlation between Inspect/OpenCode events and MLflow/OTel traces;
- re-evaluation without repeating inference;
- structured human feedback and evidence links.

If the legacy scenario needs only a small adapter, accept this composition. If
artifact-first execution or claim-level evidence repeatedly fights the selected
tools, document that concrete gap before creating a project-owned model.

# Tooling Bake-off Protocol

Status: active research protocol, 2026-08-12.

## Purpose

Determine which existing tools should be used, integrated, or excluded before
designing a new workbench domain model. The current OpenCode benchmark remains
an unchanged historical baseline during this phase.

The question is not which product has the longest feature list. It is whether
a free, Linux-compatible combination can compare complete ways of solving a
task without forcing every task into a prompt-response shape.

## Eligibility

A foundation candidate must:

- run locally on Linux without a paid account or commercial database;
- have an OSI-style permissive open-source licence;
- retain raw data locally and make network egress explicit;
- expose a documented export or API suitable for migration;
- accept external programs and artifacts, not only hosted LLM calls.

The repository must remain machine-independent: after cloning on another
Linux host, a contributor should be able to select a lightweight or extended
profile and reproduce the experiment. CPU, GPU, memory, disk, drivers, and
power sensors are execution metadata, not architectural assumptions. Missing
hardware measurements must degrade to `unknown`, not prevent a run.

Open-core and source-available products may be evaluated as optional viewers,
but cannot become mandatory infrastructure. Paid model inference is allowed
when the experiment records its cost; paid infrastructure is not.

## Scenarios

### S1: Existing coding benchmark

Treat one OpenCode execution as a black-box candidate. Preserve its workspace,
JSONL trace, diff, grader output, timing, token and cost observations. Test
whether a candidate tool can reference or import these artifacts without
rewriting `run_agent.py` around that tool.

### S2: Domain-neutral evidence report

Give a candidate several small text artifacts containing overlapping and
partially conflicting facts. Its output is a report whose claims cite source
artifact identifiers. Evaluate it with deterministic checks, a stored human
rubric, and optionally a model reviewer. Run at least two candidate strategies
and two repetitions. No coding-agent assumptions are allowed in the task
definition.

Multimodal files are represented as artifacts in this phase; actual image,
audio, and video inference is deferred until the artifact model is understood.

## Tracks

1. **Record and evaluation:** MLflow first; self-hosted Opik if its operational
   cost is reasonable. Compare runs, artifacts, datasets, evaluations, manual
   feedback, system metrics, API access, and export.
2. **Evaluation harness:** current runner, Inspect AI, and Promptfoo. Compare
   arbitrary executors, repetitions, isolation, deterministic and human
   scoring, failure handling, and log portability.
3. **Telemetry:** OpenTelemetry plus OpenInference conventions. Do not invent a
   competing span vocabulary.
4. **Resources:** provider-reported tokens/cost, MLflow system metrics, and
   CodeCarbon as an optional estimate. Unknown values remain unknown.

## Evidence to Record

For every tool, record the exact version and date, licence, required services,
Linux installation path, account requirement, default egress, setup time,
disk footprint, glue code, natural-fit observations, export path, and lock-in
risk. Record a reproducible bootstrap command or compose profile. Separate
documentation claims from behavior observed on a particular machine.

## Decision Gates

- Prefer one canonical writer; avoid permanent dual-write integrations.
- Use adapters at process and artifact boundaries before library-level
  coupling.
- Reject required hosted services, enterprise-only essentials, or opaque data
  export.
- Build a project-owned subsystem only when the same material gap occurs in
  both scenarios and no small adapter closes it.
- Do not build a trace viewer, generic scorer framework, prompt manager,
  workflow engine, or results database during this bake-off.

The output of the phase is a fact matrix and short architecture decisions, not
a refactor of the prototype.

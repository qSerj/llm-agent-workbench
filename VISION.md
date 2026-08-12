# Vision

LLM Agent Workbench is a local-first research laboratory for comparing complete
ways of solving a task. A candidate can be one model, a coding agent, a normal
program, a multi-agent pipeline, a local/cloud hybrid, or a human-assisted
process. The workbench compares outcomes, evidence, money, time, tokens, and
local resources without assuming that every execution is an LLM chat.

The current `prototype-r4.2` is a useful OpenCode benchmark over a synthetic C#
repository. It is the historical starting point, not the product boundary.

## Research Question

How should intelligence, context, verification, tools, and local computation be
distributed so that a workflow reaches the required quality with the least
practical cost and risk?

This includes model routing, context routing, decomposition, parallelism,
verification, caching, and escalation to a stronger model or a person. A tool
call has no fixed token price: the relevant cost is the inference and context
that follow it, plus every retry and downstream stage.

## Experiment Shape

The working vocabulary is deliberately conceptual until the tooling bake-off
shows which objects must be owned by this project:

```text
Experiment
  task intent and evaluation policy
  cases with versioned input artifacts
  candidate workflow versions
  repetitions
  executions with outputs and resource observations
  deterministic, model-based, and human evaluations
```

Artifacts may be text, source trees, tables, images, audio, video, or generated
files. Evaluation may inspect an answer, an output artifact, the execution
trajectory, external tests, source support, or human judgement. Unsupported
modalities must remain opaque artifacts rather than being forced into strings.

## Evidence and Provenance

The project distinguishes two questions:

1. **Execution provenance:** which activity, agent, tool, model, and source
   artifact produced an output. OpenTelemetry/OpenInference and established
   provenance standards should cover this where possible.
2. **Epistemic evidence:** which source supports or contradicts a particular
   claim. This is a quality property, not merely another trace span.

Raw traces and source artifacts remain authoritative. Summaries and scores are
indexes; a perfect deterministic score must not erase an unsupported claim.

## Reuse Before Build

This project does not aim to replace MLflow, Inspect AI, Promptfoo, Opik,
OpenTelemetry, or mature workflow engines. In particular, it should not grow
its own generic trace store/viewer, prompt manager, LLM cost dashboard, scorer
framework, human annotation application, or orchestration engine unless a
repeated measured gap requires one.

Foundation dependencies must be permissive open source, free to run locally on
Linux, usable without a commercial database or account, and exportable.
Open-core and source-available tools can be optional integrations. Paid model
inference is valid experimental input; mandatory paid infrastructure is not.

The likely result is a small composition layer: reproducible manifests,
adapters for arbitrary executors and artifacts, and portable correlation IDs
across selected tools. It may not be a standalone platform at all.

## Development Path

### 0. Preserve the baseline

Keep `prototype-r4.2` runnable and its limitations explicit. Do not refactor it
while the target architecture is still under investigation.

### 1. Tooling bake-off (completed first pass)

Run a legacy coding case and a domain-neutral evidence-report case through
MLflow, Inspect AI, Promptfoo, and an operational review of self-hosted Opik.
Measure installation weight, Linux ergonomics, data egress, artifacts, repeats,
failure handling, evaluation, feedback, telemetry, and export. See
[the protocol](docs/research/bakeoff-protocol.md).

### 2. Minimal composition experiment (current)

Select one canonical writer and one evaluation/execution path. Build only the
small adapters needed to run the two scenarios reproducibly. Export execution
telemetry using OpenTelemetry/OpenInference rather than a private span format.

The second research slice has validated partial-failure import, real OTLP/HTTP
protobuf export, and binary audio artifacts evaluated outside an LLM workflow.
Actual human review is the remaining gate. See the
[composition results](docs/research/composition-results-2026-08-12.md) and the
[portable-envelope decision](docs/decisions/0003-portable-execution-envelope.md).

### 3. Economical pipelines

Compare single-solver, solve-review-fix, independent-solvers-plus-judge, and
planner-workers-verifier strategies. Attribute every planner, worker, reviewer,
retry, tool, and failure to the whole workflow.

### 4. Context and model routing

Test whether indexes, verified summaries, targeted excerpts, local workers,
and confidence-based escalation preserve quality while reducing context and
cloud cost.

### 5. Broader modalities and domains

Add real image, audio, video, document, and structured-data cases only after
artifact transport and evaluation boundaries work for both existing scenarios.
Each domain earns its own ground truth, risks, and human-review policy.

## Measurement Rules

- Unknown stays unknown; estimates are labelled with their method and inputs.
- Compare the whole workflow, including failed and abandoned attempts.
- Record provider/model versions and the machine profile with every execution.
- Hardware capabilities affect measurements, not whether an experiment is
  structurally valid.
- Keep raw data local by default and make every external data boundary explicit.

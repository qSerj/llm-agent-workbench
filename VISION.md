# Vision

LLM Agent Workbench is intended to become a small, local-first laboratory for
measuring and designing economical agent systems. It starts from a practical
benchmark, not from a general-purpose agent framework.

## Core question

How should intelligence, context, verification, and tools be distributed so
that a workflow reaches the required quality with the least practical cost,
latency, token use, and local compute?

The workbench should make those trade-offs observable rather than anecdotal.
One run must preserve enough evidence to explain not only whether it succeeded,
but how it spent its budget and where it failed.

## Product direction

1. **Results core and CLI.** Define a stable run model; discover existing
   result directories; classify complete, failed, and partial runs; expose
   `list`, `show`, `compare`, and guarded `delete` operations.
2. **Thin local UI.** Browse runs, filter by model/provider/task/status, compare
   metrics, and inspect an event timeline without hiding raw artifacts.
3. **Pipelines.** Add reproducible solve-review-fix, independent-solvers-plus-
   judge, and planner-workers-verifier workflows. Attribute time, tokens, cost,
   tools, and failures to every stage and to the pipeline as a whole.
4. **Model and context routing.** Use expensive models only for decisions that
   require them; provide workers with narrow, evidence-based context instead of
   repeatedly sending an entire repository or corpus.
5. **Domain-neutral experiments.** Describe work as tasks, input artifacts,
   allowed tools, expected outputs, and evaluation so the same machinery can
   support code, documents, research, reconciliation, and other domains.

## Design principles

- Raw traces and source evidence remain authoritative; summaries are indexes.
- Unknown measurements remain unknown. Never invent provider prices or energy
  readings.
- Comparisons include the whole workflow, including planners, retries,
  reviewers, judges, and failed attempts.
- Local and cloud execution are first-class, including explicit data-boundary
  choices for private inputs.
- Storage and orchestration APIs precede UI complexity.

The current `prototype-r4.2` implements only the initial single-agent benchmark
and telemetry collection. It is preserved as the historical starting point.

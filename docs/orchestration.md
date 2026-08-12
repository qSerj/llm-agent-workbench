# Multi-model Orchestration Notes

These are design directions, not features implemented by `prototype-r4.2`.
Every pipeline should preserve stage-level artifacts and whole-pipeline time,
token, tool, cost, energy, retry, and failure totals.

## Solver, reviewer, fixer

The safest first pipeline experiment is:

```text
solver -> structured reviewer findings -> fixer -> deterministic grader
```

The solver produces the requested artifact. A reviewer, preferably from a
different model family, checks claims against source and emits structured
findings rather than rewritten prose. The fixer receives the original evidence,
result, and findings and may edit only the allowed output. Preserve `solver/`,
`reviewer/`, `fixer/`, and `final/` separately.

## Independent solvers and judge

For higher-stakes tasks, run two independent solvers and ask a judge to compare
their factual claims against source. The judge should make a structured
selection or decision; it should not blindly merge text. A final writer may
render the accepted facts.

## Planner, workers, verifier

A strong model can receive a high-level goal and compact repository map, then
emit a dependency-aware task graph for cheaper or local workers. Every worker
task needs narrow scope, explicit evidence targets, allowed tools, an output
schema, dependencies, and acceptance criteria. A verifier promotes only facts
confirmed against authoritative input. The strong model returns only for
planning, unresolved disputes, or final judgment.

## Hierarchical context

Large inputs should be indexed progressively:

```text
source -> symbols -> factual summaries -> subsystem maps -> task context
```

Summaries are navigation aids, not truth. A model should receive the smallest
set of relevant source excerpts, call paths, and verified facts needed for its
task. This reduces cost and latency while limiting irrelevant context.

## Security boundary

A cloud planner cannot safely decompose proprietary source when decomposition
requires seeing that source. Possible splits include a local indexer producing
approved structural metadata for a cloud planner, followed by local workers,
or an entirely local planner/worker/reviewer chain. Data exposure must be an
explicit pipeline property rather than an incidental provider choice.

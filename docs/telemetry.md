# Telemetry and Limitations

The prototype preserves raw OpenCode JSON events and derives a compact summary
from them. Derived values are best-effort observations, not normalized billing
or hardware measurements.

## Per-task artifacts

Each `taskNN/` directory contains:

- `prompt.md` and `effective_model.txt` — requested work and resolved provider
  model;
- `opencode.jsonl` — the complete captured event stream;
- `exit.json` — return code, wall time, tool/token/cost counts, and optional
  energy estimate;
- `git.diff` and `git.status.txt` — observable workspace changes;
- `grade.json` — deterministic grader output;
- `workspace/` — the complete isolated repository after the agent exits.

The run-level `metadata.json` records requested parameters, while
`run_summary.json` aggregates all selected tasks.

## Tool calls and tokens

`tool_calls` counts OpenCode `tool_use` events. `failed_tool_calls` counts events
whose final state is `error` or `failed`. This measures reported events, not
semantic usefulness.

The tool operation itself has no universal token cost. Returned data normally
becomes part of a later model input along with system instructions, tool
definitions, and accumulated history. The runner sums numeric token fields from
reported `step_finish` events and also keeps the final reported token object.
Providers may differ in whether cached, reasoning, or other token categories
are included, so cross-provider totals are not guaranteed to be equivalent.

## API cost

When `step_finish.part.cost` is numeric, the runner treats it as a per-step
charge and sums it into `total_reported_cost_usd`. It does not consult a price
table or infer cost from tokens. If the provider reports no cost, the value is
`null`; a multi-task total is marked partial when only some tasks report cost.

This assumption matches observed OpenCode/OpenRouter traces for the prototype.
If a provider emits cumulative rather than per-step values, the sum will be
wrong. Preserve the JSONL trace so the interpretation can be audited later.

## Time and local energy

`wall_seconds` measures elapsed runner time around the OpenCode process. The
run total is the sum of serial task wall times.

When `--power-watts W` is supplied:

```text
estimated_kWh = W * wall_seconds / 3,600,000
```

Optional electricity cost multiplies that estimate by `--electricity-rate`.
This represents an assumed average whole-PC draw. For meaningful comparison,
measure power externally, record idle/load methodology, and keep machine and
runtime settings consistent.

## Comparison guidance

- Run the same task, fixture revision, permissions, and grader.
- Pin a specific model rather than a routing alias.
- Repeat noisy experiments and retain failures.
- Compare score and evidence alongside cost; a cheap incomplete run is not an
  equivalent result.
- For future pipelines, include planners, workers, reviewers, retries, judges,
  and verification in whole-workflow totals.

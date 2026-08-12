# Legacy OpenCode Import: 2026-08-12

This is the second scenario from the
[bake-off protocol](bakeoff-protocol.md): an existing coding-agent execution is
treated as an external black box rather than rewritten around a tracking SDK.

## Execution

- OpenCode `1.18.16` standalone CLI on Linux.
- LM Studio with `openai/gpt-oss-20b`, fully GPU-loaded, 32,768-token context.
- Task 1 completed in 14.46 seconds with return code 0.
- OpenCode reported 11 tool calls, one failed `read`, and 12 model steps.
- Summed step usage was 111,860 input, 1,158 output, and 121 reasoning tokens.
- Provider-reported cost was zero. Energy remains unknown because no meter or
  defensible average-power input was supplied.
- The deterministic grader returned 16/16 and confirmed that `src/` was
  unchanged.

An earlier smoke test at an 8,192-token context answered correctly, then entered
repeated compaction/continuation steps. The first inference already contained
6,130 input tokens. A 32,768-token run avoided that behavior. This is evidence
of a context/harness interaction, not a universal minimum context requirement.

## Quality Finding

The perfect deterministic score masked a factual problem. The generated report
invented a usage example in which `TableInterleaverProfile` is sent through an
`IRegisterTransport.WriteRegisters()` call. The cited source actually creates a
`SimpleInterleaverProfile` and calls `DeviceController.ApplyInterleaverProfile`.

This validates the separation between a score and claim-level source support.
The grader remains useful, but cannot be the sole authority for factual output.

## Artifact Finding

The raw run contains the prompt, JSONL events, workspace, grading output,
metadata, and summaries. Its `git.diff` is empty because the generated `docs/`
directory is untracked. The workspace preserved the document, but a diff-only
consumer would lose the primary output. Artifact capture must therefore be
authoritative; VCS diffs are only derived views.

## MLflow Import

A disposable adapter imported the unmodified run into MLflow `3.13.0`:

- one run retained stable task, case, and candidate identifiers as parameters;
- the complete 416,688-byte raw run became an artifact tree;
- deterministic metrics and token/cost observations remained unchanged;
- one external-execution trace used timestamps from OpenCode JSONL;
- tags correlated the MLflow run, trace, and source run directory;
- a source-grounded judge assessment recorded the unsupported usage example;
- no inference was repeated during import or assessment.

The trace covered 11.91 seconds while runner wall time was 14.46 seconds. Both
are valid: one describes observed model/tool events and the other includes
runner overhead. They must not be silently collapsed into one latency metric.

## Decision Impact

MLflow is adequate as the canonical record for both evaluated scenarios.
Inspect remains the natural harness for candidates built with Inspect, but an
existing OpenCode or arbitrary executable need not be forced through it. A
small adapter can import the external execution directly.

Follow-up tests covered failed/partial execution import, OpenTelemetry export,
and binary audio artifacts. Actual human review remains open. See the
[minimal composition results](composition-results-2026-08-12.md). No
project-owned storage, trace viewer, scorer framework, or workflow engine is
justified.

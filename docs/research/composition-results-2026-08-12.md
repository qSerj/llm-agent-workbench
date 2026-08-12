# Minimal Composition Results: 2026-08-12

This follow-up tested the remaining integration boundaries without changing the
historical runner. Disposable adapters and databases lived under `/tmp`; the
source run bundles remain under the ignored `agent_runs/` directory.

## Partial and Failed Execution

A synthetic OpenCode-compatible process wrote an incomplete document, emitted
three valid events plus one stderr line, and exited with code 7. The existing
runner preserved the workspace, prompt, raw stream, status, and grade of 7/16.
Its token summary retained the reported 120 input, 20 output, and 10 reasoning
tokens instead of discarding the failed attempt.

The import adapter initially assumed that `opencode.jsonl` was pure JSONL and
failed. In practice it is a merged stdout/stderr capture. The corrected import
preserved the byte-for-byte stream, indexed valid events, counted malformed
lines, marked the execution and trace as failed, and attached a code assessment
describing incompleteness. A failed execution is a first-class observation,
not a missing run.

## Portable Execution Trace

The successful legacy run was reconstructed with OpenTelemetry SDK `1.44.0`
and sent by the official OTLP/HTTP exporter to a disposable loopback receiver.
The captured 19,967-byte protobuf decoded through the official OTLP schema as:

- one trace and one root `task.execute` span;
- 12 child model-step spans;
- 11 tool spans;
- one error-status tool span, matching the failed tool call.

The projection used current GenAI attributes for operations, agent, model,
tools, and token usage, plus `openinference.span.kind` for `AGENT`, `LLM`, and
`TOOL`. Workbench-only observations were namespaced because the GenAI semantic
conventions are still evolving. This demonstrates a standards-compatible
export boundary; it does not make OTLP the source format. Raw events retain
provider-specific detail and remain authoritative.

## Binary Artifact Experiment

A domain-neutral task asked candidates to convert a stereo 48 kHz WAV to mono
16 kHz FLAC without changing its two-second duration. Both candidates were
ordinary `ffmpeg` programs, not LLMs. `ffprobe` performed four deterministic
checks, while MLflow `3.13.0` recorded task/case/candidate identities, commands,
hashes, binary inputs and outputs, evaluation JSON, wall time, and CPU time.

| Candidate | Score | Wall | Output |
| --- | ---: | ---: | ---: |
| correct conversion | 4/4 | 0.053 s | 21,174 bytes |
| truncated, unconverted audio | 1/4 | 0.051 s | 28,508 bytes |

The failing candidate still produced a valid FLAC, but failed sample-rate,
channel, and duration requirements. This is why an artifact's media type and
existence are not substitutes for task-specific evaluation.

## Model Boundary

The experiments support a narrow project-owned interchange envelope rather
than a new platform database:

```text
execution identity and status
task, case, candidate, repetition identities
input/output artifact references, media types, sizes, and hashes
typed observations with units and measurement methods
evaluations with subject, rubric version, source type, value, and rationale
correlation IDs for raw bundles, MLflow records, and OTel traces
```

MLflow remains the queryable experiment and artifact record. OTLP is the
portable execution-telemetry projection. Inspect and Promptfoo remain optional
harnesses for their natural task shapes. None of these should define the
project's task intent or force binary artifacts into text cells.

## Remaining Check

A coarse MLflow trace has been prepared for a real human review of the legacy
report. MLflow feedback is trace/span-centred, while the workbench conceptually
attaches evaluation to an execution, output artifact, claim, or trajectory.
The first human assessment will test whether a small correlation adapter is
sufficient or whether that mismatch becomes a repeated domain-level gap.

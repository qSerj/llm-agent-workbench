# Current Research State

Checkpoint: 2026-08-12. This document is the handoff point for continuing on
another machine or in another session.

## Where We Stopped

The historical `prototype-r4.2` remains unchanged as a working OpenCode/.NET
benchmark. Research has moved the intended product boundary away from “another
agent UI” toward a small composition layer for comparing complete workflows.

The current provisional composition is:

```text
project-owned execution envelope
  ├─ records task/case/candidate/repetition identity
  ├─ references arbitrary input and output artifacts
  ├─ records status, observations, evaluations, and correlations
  ├─ projects queryable records and artifacts into MLflow
  └─ exports execution activity as OpenTelemetry OTLP
```

MLflow is the provisional canonical experiment record. OpenTelemetry and
OpenInference supply trace vocabulary and transport. Inspect AI and Promptfoo
remain optional harnesses for tasks that naturally fit them. No custom database,
trace UI, evaluator framework, or workflow engine is currently justified.

Hands-on experiments have covered a successful OpenCode run, a partial failed
run, real OTLP/HTTP protobuf export, and an audio task with binary WAV/FLAC
artifacts produced by ordinary programs. The details and measurements are in
[the composition results](research/composition-results-2026-08-12.md).
Earlier model runs and their preliminary role assessments are preserved in
[the model observations](research/model-observations-before-workbench.md).

On the current work machine, the GTX 960 2 GB is not a practical LLM accelerator
even when its desktop driver is active. Prefer OpenRouter and GigaChat for
interactive experiments. Treat local GPT-OSS/Nemotron runs as deliberate
privacy, fallback, or unattended-batch cases rather than the default path.

## Exact Next Step

Complete one genuine human assessment of the legacy generated report. Record
four 0–2 scores (`correctness`, `coverage`, `evidence`, `usefulness`), a
`PASS`/`FAIL` verdict, rationale, reviewer identity, rubric version, and the
evaluated execution/output correlation. Do not synthesize this assessment with
code or an LLM.

Then decide the concrete serialization and validation rules for version 1 of
the execution envelope. Start implementation only after that decision. The
first implementation should be a small reproducible adapter, not a platform or
UI. Economical multi-agent pipelines and context/model routing follow after the
envelope works end to end.

## Continuing on Another Machine

Normal design and repository work requires only cloning/pulling this small Git
repository. Baseline validation uses Python 3 and the .NET 8 SDK:

```bash
python3 -m unittest discover -s tests -v
dotnet build fixture/InterleaverBench.sln -m:1
```

Do not install the entire bake-off stack up front. The measured cold footprints
on this host were roughly 649 MB for MLflow, 242 MB for Inspect AI, and 1.4 GB
for Promptfoo; local model files can add many more gigabytes. These tools and
models are not committed and are not required to read the findings or design
the envelope. Install only MLflow when the next persistent adapter actually
needs it; Inspect, Promptfoo, LM Studio models, and OpenCode are optional for
repeating their respective experiments.

Temporary adapters, SQLite databases, OTLP payloads, and generated audio lived
under `/tmp` and are intentionally absent from Git. Raw benchmark executions
under `agent_runs/` are also ignored. Their important observations are captured
in committed research notes; exact experimental reproduction will require new,
deliberately maintained adapters rather than copying this machine's temporary
environment.

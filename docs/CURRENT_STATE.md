# Current Research State

Checkpoint: 2026-08-13. This document is the handoff point for continuing on
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

The first genuine human review is now recorded in
[the human assessment](research/human-assessment-legacy-task01-2026-08-13.md).
It confirmed that a formally perfect result can contain a factual defect and
that an overall verdict must remain separate from optional quality dimensions.
The concrete envelope v1 serialization and evaluation rules are implemented in
[ADR 0004](decisions/0004-envelope-v1-serialization-and-evaluation.md): UTF-8
JSON validated by JSON Schema Draft 2020-12, with raw artifacts authoritative.

On the current work machine, the GTX 960 2 GB is not a practical LLM accelerator
even when its desktop driver is active. Prefer OpenRouter and GigaChat for
interactive experiments. Treat local GPT-OSS/Nemotron runs as deliberate
privacy, fallback, or unattended-batch cases rather than the default path.

The named shortlist to retain across future experiments is:

- **Xiaomi MiMo v2.5** (OpenRouter): fast, inexpensive worker; verify facts;
- **DeepSeek V4 Flash** (OpenRouter): careful solver and reviewer;
- **GLM-4.7 Flash** (OpenRouter): useful alternative; constrain interpretation;
- **GigaChat-3-Ultra** (Sber via `gpt2giga`): strong, fast agent candidate.

## Exact Next Step

Envelope v1 now validates the successful and partial legacy runs plus freshly
reproduced correct and defective binary-audio candidates. The adapters verify
artifact hashes, import queryable records and artifacts into MLflow, and export
real OTLP/HTTP protobuf with correlation IDs. Usage is documented in
[the envelope v1 guide](envelope-v1.md).

The first solver-reviewer-fixer comparison is complete. Its Russian-language
[results](research/solver-reviewer-fixer-results-2026-08-13.ru.md) include both
a regression from a loose review policy and an improvement from an explicit
evidence policy. The same reviewer model produced opposite verdicts. A cheap
programmatic citation check also caught a new error introduced by the fixer.

The next narrow design step is to represent stage and revision relationships
without adding a workflow engine: link the solver output, reviewer findings,
fixer input/output, and aggregate observations across the complete candidate.
Then repeat the strict policy with targeted context or claim selection to test
whether the quality gain can be retained below the measured 5.75x API-cost and
4.39x wall-time multipliers.

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

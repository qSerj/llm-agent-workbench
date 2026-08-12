# Bake-off Results: 2026-08-12

This is the first recorded hands-on research slice under the
[bake-off protocol](bakeoff-protocol.md). Temporary environments and generated
results lived under `/tmp` and were not added to the repository. The observed
behavior informs the provisional decision; reproducibility is the job of the
minimal adapters in the next phase, not a claim made for this disposable setup.

## Host and Bootstrap

- Linux x86_64, Python 3.13.5, .NET 8 fixture.
- NVIDIA RTX 4070 Ti SUPER visible on PCI; NVML unavailable to this session.
- Node changed from system `v20.19.2` with npm prefix `/usr/local` to user-local
  `fnm 1.39.0`, Node `v24.19.0` LTS, npm `11.17.0`. No `sudo` is needed for npm
  packages managed by this Node installation; the system Node was not removed.
- Cold dependency environments: MLflow about 649 MB, Inspect about 242 MB,
  Promptfoo about 1.4 GB. Download time was dominated by the network and should
  not be interpreted as steady-state runtime cost.

These figures describe this host, not minimum requirements. Another Linux
machine may use a different CPU, GPU, Python/Node installation, or lightweight
profile and still execute the same experiment structure.

## Domain-neutral Scenario

Two cases used small text artifacts with conflicting thermal and retention
rules. Two deterministic candidates ran twice. The policy-aware candidate cited
the controlling sources and detected conflicts; the naive candidate did not.
The point was framework behavior, not candidate intelligence.

### MLflow 3.13.0

- Recorded eight runs in local SQLite with case, candidate, repetition, metrics,
  input artifacts, output report, and human rubric.
- Captured one-span execution traces and then re-evaluated stored outputs with a
  custom GenAI scorer. The database contained 16 traces after execution and
  evaluation; evaluated traces held code assessments.
- Accepted structured HUMAN feedback with reviewer identity, rationale, and
  rubric metadata.
- Captured CPU, memory, disk, and network metrics. GPU metrics were skipped.
- Served the local UI/API on `127.0.0.1`; `/health` and experiment search passed.
- Required installing `psutil` separately for system metrics. Telemetry was
  disabled and verified through the SDK.

### Inspect AI 0.3.258

- Ran `2 cases x 2 candidates x 2 epochs` without any model provider.
- Produced two compact `.eval` files (about 11 KB each) with transcript, custom
  multi-value scores, aggregate means, and export/viewer tooling.
- The restricted sandbox blocked its optional local control socket, but Inspect
  warned and completed the evaluations correctly.
- A custom non-model solver is easy, but the final value still occupies a
  `ModelOutput`; external artifacts need an explicit adapter.

### Promptfoo 0.121.15

- One YAML file and one Python provider produced eight result rows, named
  assertions, local SQLite state, and JSON export.
- Four expected passes and four expected failures returned exit code 100, while
  runtime errors use a different code.
- Offline posture required explicit telemetry, update, remote-generation, and
  sharing flags. These controls are not a network sandbox.
- Best fit: prompt/API regression and compact CI matrices, not arbitrary output
  artifact management.

## Opik 2.0.49 Operational Review

The pinned Compose configuration resolves to eleven services. Three Opik amd64
application images alone contain about 1.04 GB of compressed layers: backend
about 501 MB, Python backend about 472 MB, and frontend about 64 MB. Required
infrastructure adds MySQL, ClickHouse, Redis, MinIO, ZooKeeper, and helpers. The
Python backend is privileged and backend usage reporting defaults to enabled.

This remains a legitimate Apache-2.0 optional observability backend. A full pull
and startup was deferred because the lighter candidates already covered the
current scenario and Opik had not yet demonstrated a missing capability.

## Legacy Scenario

After LM Studio was started, OpenCode `1.18.16` was installed as a user-local
standalone CLI and GPT-OSS 20B was loaded with a 32,768-token context. Task 1
completed in 14.46 seconds and scored 16/16, but source review found an invented
usage example that the deterministic grader missed.

The complete run was imported into MLflow without changing the runner. Raw
JSONL, workspace, grading, metrics, and summaries remained available; an
external-execution trace retained source timestamps and accepted an additional
source-grounded assessment without repeating inference. See the
[legacy import report](legacy-opencode-results-2026-08-12.md).

## Outcome

The two scenarios support MLflow as the canonical record, Inspect as an agent
harness where it naturally fits, and Promptfoo as a specialized regression
tool. They do not justify project-owned storage, evaluation, UI, or
orchestration frameworks. See
[ADR 0002](../decisions/0002-provisional-tool-composition.md).

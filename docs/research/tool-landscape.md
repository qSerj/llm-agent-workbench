# Tool Landscape

Research snapshot: 2026-08-12. Versions are pinned to what was evaluated, not
promises that the latest release will always behave identically.

## Eligibility Matrix

| Tool | Version | Licence | Free local Linux | Natural role | Status |
| --- | --- | --- | --- | --- | --- |
| MLflow | 3.13.0 | Apache-2.0 | Yes; Python, SQLite, local artifacts | Runs, artifacts, traces, evaluation, feedback, system metrics | Hands-on |
| Inspect AI | 0.3.258 | MIT | Yes; Python | Agent evaluation harness, epochs, limits, sandboxes, scoring | Hands-on |
| Promptfoo | 0.121.15 | MIT | Yes; Node 24 used here | Declarative prompt/provider/test matrices and CI | Hands-on |
| Opik | 2.0.49 | Apache-2.0 | Yes; Docker Compose | LLM trace/evaluation backend and UI | Operational review |
| OpenTelemetry + OpenInference | OTel 1.44.0; conventions evolving | Apache-2.0 | Yes | Portable trace conventions and transport | Hands-on export |
| CodeCarbon | 3.2.9 | MIT | Yes; Linux is primary | Local energy/emissions estimate | Second pass |

`Hands-on` means the domain-neutral scenario in
[the protocol](bakeoff-protocol.md) was executed locally. `Operational review`
does not imply that a full service stack was accepted as project infrastructure.

## Boundary Findings

MLflow is broader than a model tracker. Its open-source local setup supports a
SQLite tracking store, arbitrary artifacts, GenAI traces, code or model-based
evaluation, trace assessments, and CPU/memory/disk/network metrics. NVIDIA GPU
metrics require NVML support. It is the strongest first candidate for the
canonical experiment record, but its GenAI evaluation API still describes the
world primarily as inputs, outputs, expectations, and traces.

Observed locally: eight executions (2 cases x 2 candidates x 2 repetitions)
were recorded in SQLite with input/output/rubric artifacts, deterministic run
metrics, traced candidate calls, and a second-pass `mlflow.genai.evaluate()`.
The scorer attached two assessments to each evaluated trace. The local server
answered its health and experiment APIs on loopback. CPU, memory, disk, and
network metrics were captured; GPU metrics were correctly skipped because NVML
was unavailable to the session. Full MLflow plus the added `psutil` dependency
occupied about 649 MB in its isolated environment; the resulting tiny research
dataset occupied about 1 MB across the database and artifacts.

MLflow open source also enables anonymized usage telemetry by default from
version 3.2. Bake-off commands set `MLFLOW_DISABLE_TELEMETRY=true` and verify
that the telemetry client is absent. A future bootstrap must make this local-
first setting explicit for both SDK and UI processes.

Inspect AI maps cleanly to repeatable agent evaluation: dataset items are
cases, solvers are candidate strategies, epochs are repetitions, and scorers
can be deterministic or model-based. It also has budgets, sandboxing, rich eval
logs, and a local viewer. Its `TaskState` is conversation/model-output centred,
so non-text output artifacts need an explicit adapter rather than becoming the
project's universal artifact model by accident.

Observed locally: a two-case, two-candidate, two-epoch evaluation ran without a
model provider. Inspect produced compact `.eval` logs and aggregated the custom
evidence/conflict scores as expected. The thin adapter was about the task,
solver, and scorer, not a storage layer. Pinning matters: an unpinned install on
the research date resolved to 0.3.258, newer than the previously indexed PyPI
page. Its optional control server could not open inside the restricted sandbox,
but evaluation and log writing continued correctly.

Promptfoo provides the shortest declarative path for comparing prompts,
providers, assertions, and repetitions. Python and shell providers can wrap an
arbitrary executable, but the primary result cell remains a rendered textual
output. It is useful for prompt/API regression suites, not an obvious universal
workflow substrate. Its supported Node runtime was newer than the machine's
system Node; a user-local `fnm` installation solved this without `sudo`.

Observed locally: one YAML file plus a small Python provider produced the full
2 cases x 2 candidates x 2 repeats matrix, named assertion scores, a local
SQLite database, and JSON export. The expected half-failing comparison exited
with code 100 rather than a generic runtime failure, which is useful in CI but
must be handled explicitly by a wrapper. The cold local `node_modules` tree was
about 1.4 GB, much heavier than the terse `npx` quick start suggests.

Promptfoo telemetry and update checks are enabled by default. Offline use needs
several documented flags, and those flags are not a firewall. Treat configs and
custom providers as trusted code and enforce sensitive egress outside the tool.

Opik is genuinely Apache-2.0 and self-hostable, but the local full stack is not
lightweight: frontend and Java backend plus MySQL, ClickHouse, Redis, MinIO, and
ZooKeeper. That can be a good optional LLM observability backend; it is too much
to make a mandatory dependency before it demonstrates a material advantage
over MLflow for our two scenarios.

OpenTelemetry/OpenInference address execution telemetry, not experiment intent
or epistemic evidence. They should define export vocabulary for LLM, agent,
tool, evaluator, and workflow spans. They should not dictate how task cases,
candidate versions, human rubrics, or output artifact comparisons are modeled.

Observed locally: the official OpenTelemetry OTLP/HTTP exporter sent a
reconstructed OpenCode execution as protobuf, which decoded into one trace with
one root, 12 model-step, and 11 tool spans. GenAI and OpenInference attributes
coexist cleanly, while project-only resource and evaluation observations remain
namespaced. OTLP is therefore a viable export projection, not a replacement
for the raw executor event stream.

CodeCarbon can read Linux RAPL CPU counters and NVIDIA NVML data when the host
exposes them; otherwise it estimates from hardware/TDP and load. Its result
must therefore carry a measurement-method label. On this host the RTX 4070 Ti
SUPER is visible on PCI but NVML is not currently usable from the session, and
no readable RAPL counters were found. A number from fallback mode cannot be
presented as a hardware energy measurement.

## Licence and Product Tiers

The table above contains foundation-eligible permissive open source. Langfuse
is an optional comparison because its repository combines an MIT core with
enterprise code and its current self-hosted stack is substantial. Phoenix uses
the Elastic License 2.0, so it is source-available rather than foundation-
eligible under this project's policy. Cloud-only services and features that
require commercial infrastructure are excluded.

Paid inference remains allowed. A candidate may call OpenRouter or another
provider as long as the execution records provider, model, observed tokens,
reported monetary cost, and data-boundary choice. Infrastructure must work
without buying a subscription.

## Sources

- [MLflow architecture](https://mlflow.org/docs/latest/self-hosting/architecture/overview/),
  [system metrics](https://mlflow.org/docs/latest/ml/tracking/system-metrics/),
  [GenAI evaluation](https://mlflow.org/docs/latest/genai/eval-monitor), and
  [usage tracking](https://mlflow.org/docs/latest/community/usage-tracking/)
- [Inspect tasks](https://inspect.aisi.org.uk/tasks.html),
  [solvers](https://inspect.aisi.org.uk/solvers.html), and
  [log viewer](https://inspect.aisi.org.uk/log-viewer.html)
- [Promptfoo CLI](https://www.promptfoo.dev/docs/usage/command-line/),
  [offline settings](https://www.promptfoo.dev/docs/faq/#how-can-i-use-promptfoo-in-a-completely-offline-environment),
  and [security model](https://github.com/promptfoo/promptfoo/security)
- [Opik local deployment](https://www.comet.com/docs/opik/self-host/local_deployment/)
  and [repository](https://github.com/comet-ml/opik)
- [OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai),
  [agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md),
  and the [OpenInference specification](https://arize-ai.github.io/openinference/spec/)
- [MLflow feedback collection](https://mlflow.org/docs/latest/genai/assessments/feedback/)
- [CodeCarbon methodology](https://mlco2.github.io/codecarbon/methodology.html)

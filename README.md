# LLM Agent Workbench

[Русская версия](README.ru.md)

LLM Agent Workbench is an early research prototype for running the same
repository task through different agent models and providers, then comparing
quality, latency, tool use, token usage, API cost, and estimated local energy.

This repository captures the working `r4.2` prototype from which the larger
workbench will grow. It is useful today as a small OpenCode benchmark runner;
it is not yet the result-management application described in [VISION.md](VISION.md).

## What works today

- LM Studio, OpenRouter, and arbitrary OpenAI-compatible endpoints.
- Identical prompts and an isolated Git workspace for every task.
- Restricted OpenCode permissions: agents may inspect the fixture but edit only
  `docs/**`.
- Automatic grading and preservation of the complete JSONL trace, diff, status,
  timing, tool counts, reported tokens and provider-reported costs.
- Optional local energy and electricity-cost estimates based on an assumed
  average whole-PC power draw.

## Requirements

- Python 3.10 or newer (standard library only)
- [OpenCode](https://opencode.ai/) available as `opencode`
- .NET 8 SDK to validate the included C# fixture
- LM Studio CLI (`lms`) only for `--provider lmstudio`

Provider credentials must be configured outside this repository. See
[Provider setup](docs/providers.md) before the first real run.

## Quick start

Check the local environment without calling a model:

```bash
python3 run_agent.py --version
python3 -m unittest discover -s tests -v
dotnet build fixture/InterleaverBench.sln -m:1
```

Run task 1 through a specifically selected OpenRouter model:

```bash
python3 run_agent.py \
  --provider openrouter \
  --model openai/gpt-oss-120b:free \
  --tasks 1 \
  --tag first-run
```

Run against a local OpenAI-compatible proxy:

```bash
python3 run_agent.py \
  --provider compatible \
  --provider-id local \
  --base-url http://127.0.0.1:8090/v1 \
  --model GigaChat-3-Ultra \
  --tasks 1,2,3
```

Use the exact model identifier exposed by your provider. A full command
reference is available through `python3 run_agent.py --help`.

## Repository layout

```text
run_agent.py             benchmark runner and telemetry collection
grade.py                 deterministic task grader
tasks/                   prompts shared by all models
fixture/                 synthetic .NET 8 repository under test
tests/                   offline unit tests for runner behavior
docs/                    provider and telemetry documentation
providers.example.json   secret-free configuration examples
```

Every run is stored under `agent_runs/<timestamp>_<provider>_<model>/`. Each
task contains the prompt, effective model, raw `opencode.jsonl`, exit metadata,
Git diff/status, grade, and the complete isolated workspace. `run_summary.json`
aggregates the selected tasks. Generated runs are intentionally ignored by Git.

## Interpreting measurements

A tool call has no universal token price. Its returned content generally
affects the input of a later model inference, together with conversation
history, system instructions, and tool definitions. The runner therefore
records observable per-step telemetry instead of assigning a synthetic price
to `read`, `grep`, or another tool.

Provider cost remains `null` when OpenCode emits no explicit cost. Energy is an
estimate from user-supplied average power, not a hardware measurement. Read
[Telemetry and limitations](docs/telemetry.md) before comparing runs.

## Project status

`prototype-r4.2` is a historical baseline, not a stable release. The next
milestone is a results core and CLI for listing, inspecting, comparing, and
safely deleting runs. Multi-agent pipelines, model routing, context routing,
and a thin local UI follow after the result model is stable.

See [VISION.md](VISION.md) and [multi-agent orchestration notes](docs/orchestration.md).

## Contributing and license

See [AGENTS.md](AGENTS.md) for repository-specific development guidance.
LLM Agent Workbench is licensed under the [MIT License](LICENSE).

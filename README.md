# LLM Agent Workbench

[Русская версия](README.ru.md)

LLM Agent Workbench is a local-first research laboratory for comparing complete
ways of solving tasks by quality, evidence, time, monetary cost, and compute
resources. A candidate may be a normal program, one model, an agent, a staged
agent system, a local/cloud hybrid, or a human-assisted process.

The project reuses MLflow for experiment records and OpenTelemetry for trace
transport. Its small project-owned execution card links task, case, candidate,
artifacts, stages, observations, and evaluations without imposing an execution
engine.

## Current Structure

```text
schemas/       execution-card contract
workbench/     validation, artifact verification, integrations
tools/         MLflow and OpenTelemetry commands
examples/      reproducible domain-neutral examples
tests/         offline tests for the current core
docs/          decisions, current state, and glossary
archive/       historical C# benchmark and early research
```

## Validate

```bash
python3 -m pip install -r requirements-envelope.txt
python3 -m unittest discover -s tests -v
python3 -m py_compile workbench/*.py tools/*.py examples/audio_conversion/run.py
```

See [README.ru.md](README.ru.md) for the current detailed introduction. The
historical OpenCode/.NET prototype is preserved under
[`archive/prototype-r4.2/`](archive/prototype-r4.2/README.md) and is not part of
the active architecture.

# ADR 0001: Research Before Building a Platform

Status: accepted, 2026-08-12.

## Context

The prototype began as an OpenCode benchmark over a synthetic C# repository.
The intended research space is much wider: candidates may be models, coding
agents, scripts, multi-agent workflows, local/cloud hybrids, or human-assisted
processes; inputs and outputs may eventually include any artifact modality.

MLflow, Inspect AI, Promptfoo, Opik, and OpenTelemetry already implement large
parts of experiment tracking, evaluation, tracing, and visualization. Designing
a new results database, scorer framework, or trace UI before testing them would
create avoidable lock-in to our first coding-shaped fixture.

## Decision

Keep `prototype-r4.2` unchanged while running the two-scenario tooling bake-off.
Adopt existing permissive open-source components through process, artifact, and
telemetry boundaries wherever a thin adapter is sufficient.

Do not add a project-owned database, trace format/viewer, generic evaluator,
workflow engine, prompt manager, or large UI during this phase. A new owned
abstraction requires the same material gap to appear in both the legacy coding
scenario and a domain-neutral evidence scenario.

Machine capabilities are run metadata. No selected foundation may require a
particular GPU, RAM size, or local model; missing measurements remain unknown.

## Consequences

The next milestone produces evidence, a tool matrix, and follow-up ADRs rather
than application code. Some experiments will use adapters that are disposable.
This is intentional: their size and awkwardness are decision evidence.

The eventual architecture may be a small composition layer over existing
tools, not a standalone workbench platform. The project name does not obligate
us to own every layer.

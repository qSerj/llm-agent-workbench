# Repository Guidelines

## Project Structure & Module Organization

This repository develops a domain-neutral execution-card layer for comparing
complete task-solving methods. Historical benchmark code lives only under
`archive/prototype-r4.2/` and must not shape active modules.

User-facing discussion and new explanatory documentation should be in Russian.
Prefer terms from `docs/GLOSSARY.ru.md`; keep program, file, API-field, and code
identifiers unchanged.

- `schemas/` contains versioned JSON Schema contracts; keep v1 backward-compatible.
- `workbench/` validates cards, verifies artifacts, and projects data externally.
- `tools/` contains narrow MLflow and OpenTelemetry command-line integrations.
- `examples/` contains reproducible, domain-neutral execution examples.
- `tests/` contains offline tests for the active core.
- `docs/` contains current decisions, state, and terminology.
- `archive/` is read-only research history; do not extend it with new features.

## Build, Test, and Development Commands

Use Python 3 from the repository root:

```bash
python3 -m pip install -r requirements-envelope.txt
python3 -m unittest discover -s tests -v
python3 -m py_compile workbench/*.py tools/*.py examples/audio_conversion/run.py
python3 examples/audio_conversion/run.py --output /tmp/audio-experiment
```

The first command installs JSON Schema validation. The next two validate the
active core. The optional audio example requires `ffmpeg` and `ffprobe` and
produces execution cards outside the repository.

## Coding Style & Naming Conventions

Use four-space indentation and UTF-8. Follow PEP 8: `snake_case` for functions
and variables, `UPPER_CASE` for constants, type hints for public helpers,
`pathlib.Path` for paths, and explicit subprocess argument lists. Format JSON
with two-space indentation. Preserve unknown measurements as absent or `null`;
never silently turn them into zero.

## Testing Guidelines

Tests use `unittest` and follow `tests/test_*.py`. Cover schema validation,
semantic links, artifact tampering, stage relationships, text and binary
artifacts, and external projections where relevant. Use disposable temporary
directories and local backends. Do not commit generated MLflow databases,
media outputs, traces, credentials, or model files.

## Commit & Pull Request Guidelines

Use short imperative subjects such as `Separate historical benchmark`. Keep
schema, integration, example, and documentation changes logically focused.
Pull requests should explain the changed boundary, list validation commands,
and include a small example card or projection result when behavior changes.

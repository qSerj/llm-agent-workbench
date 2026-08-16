# Repository Guidelines

## Project Structure & Module Organization

This repository develops a domain-neutral execution-card layer for comparing
complete task-solving methods. Historical benchmark code lives only under
`archive/prototype-r4.2/` and must not shape active modules.

User-facing discussion and new explanatory documentation should be in Russian.
Prefer terms from `docs/GLOSSARY.ru.md`; keep program, file, API-field, and code
identifiers unchanged.

- `schemas/` contains versioned JSON Schema contracts; keep v1 backward-compatible.
- `workbench/` validates cards, runs multi-stage candidates, and projects data externally.
- `tools/` contains the chain runner and narrow MLflow and OpenTelemetry integrations.
- `experiments/` contains short YAML experiment descriptions.
- `ui/` is the local comparison shell; it reads envelopes and never writes them.
- `examples/` contains reproducible, domain-neutral execution examples.
- `tests/` contains offline tests for the active core.
- `docs/` contains current decisions, state, and terminology.
- `archive/` is read-only research history; do not extend it with new features.

## Build, Test, and Development Commands

Use Python 3 from the repository root:

```bash
python3 -m pip install -r requirements-lab.txt
python3 -m py_compile workbench/*.py tools/*.py examples/audio_conversion/run.py tests/*.py
python3 -m unittest discover -s tests -v
```

The first command installs JSON Schema validation and the experiment reader.
The next two validate the active core and match CI.

On a machine whose system Python has no `pip` (the case for the maintainer's
hosts), use the prebuilt `.research-env` venv instead of installing:

```bash
.research-env/bin/python3 -m unittest discover -s tests -v
```

Run an experiment and compare candidates. The runner needs PyYAML, so on a host
without `pip` use the venv here too:

```bash
.research-env/bin/python3 tools/run_chain.py experiments/solver-reviewer-fixer.yaml
.research-env/bin/uvicorn ui.app:app --port 8765     # http://127.0.0.1:8765
```

The chain runner needs `opencode` on the path and provider credentials in the
environment. The optional audio example requires `ffmpeg` and `ffprobe` and
produces execution cards outside the repository.

## Coding Style & Naming Conventions

Use four-space indentation and UTF-8. Follow PEP 8: `snake_case` for functions
and variables, `UPPER_CASE` for constants, type hints for public helpers,
`pathlib.Path` for paths, and explicit subprocess argument lists. Format JSON
with two-space indentation. Preserve unknown measurements as absent or `null`;
never silently turn them into zero.

Linting is `ruff check .`, configured in `ruff.toml` (line length 100). It is
not part of CI, so run it before finishing Python work. Ruff installs as a
standalone binary and needs no Python environment.

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

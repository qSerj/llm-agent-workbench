# Repository Guidelines

## Project Structure & Module Organization

This repository preserves an OpenCode/.NET benchmark and develops a small,
domain-neutral execution-envelope composition layer.

- `run_agent.py` configures providers, creates isolated workspaces, runs tasks, and records usage and cost data.
- `grade.py` scores a completed task workspace.
- `workbench/` validates execution envelopes and projects them to optional backends.
- `schemas/` contains versioned JSON Schema contracts; keep v1 backward-compatible.
- `tools/` contains narrow import/export CLIs; `examples/` proves non-coding artifact flows.
- `evaluations/` contains versioned assessments bound to artifact hashes.
- `tasks/01.md` through `tasks/03.md` contain the benchmark prompts; keep numbering zero-padded.
- `fixture/` is the source template copied for each run. Its C# projects live under `fixture/src/`, with the solution at `fixture/InterleaverBench.sln`.
- `tests/` contains offline unit tests; `.github/workflows/ci.yml` runs them and builds the fixture.
- `providers.example.json` documents secret-free provider configuration.
- `agent_runs/` is generated output. Do not treat run artifacts as source files.

## Build, Test, and Development Commands

Use Python 3 and the .NET 8 SDK from the repository root:

```bash
python3 run_agent.py --version
python3 -m pip install -r requirements-envelope.txt
python3 -m unittest discover -s tests -v
dotnet build fixture/InterleaverBench.sln -m:1
python3 grade.py agent_runs/<run>/task01/workspace --task 1
```

The first command confirms the runner is usable; the install supplies standard
JSON Schema validation; `unittest` checks runner and envelope behavior;
`dotnet build` validates the fixture; and `grade.py` checks one completed
workspace. A full benchmark requires OpenCode plus a configured provider.

## Coding Style & Naming Conventions

Use four-space indentation and UTF-8. In Python, follow standard library-oriented PEP 8: `snake_case` for functions and variables, `UPPER_CASE` for constants, and descriptive `argparse` option names. Prefer `pathlib.Path`, type hints for public helpers, and explicit subprocess argument lists.

For C#, retain nullable reference types and implicit usings. Use PascalCase for public types and members, `_camelCase` for private fields, and place code in the existing `Interleaver.Core` or `Interleaver.Transport` namespace. Format JSON with two-space indentation.

## Testing Guidelines

Tests use the standard-library `unittest` framework and follow `tests/test_*.py`
naming. Envelope changes must cover successful, partial, and failed executions,
artifact tampering, and both text and binary artifacts. Validate projections
against disposable local backends. Do not commit generated MLflow databases,
audio outputs, or benchmark runs.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects such as `Add partial cost reporting`, and keep unrelated runner, fixture, and documentation changes separate. Pull requests should explain the behavior change, list validation commands, identify affected providers or tasks, and include a sample summary or grading output when results change. Never commit API keys, generated `opencode.json` credentials, or large `agent_runs/` directories.

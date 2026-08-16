# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repository guidelines (structure, style, testing, commit conventions) live in AGENTS.md and are imported here:

@AGENTS.md

The rest of this file covers what AGENTS.md does not.

## Validation

**The system `python3` cannot run the tests here**: it has no `pip` and no `jsonschema`, so `unittest` fails with import errors. Use the prebuilt `.research-env` venv, which also carries PyYAML, MLflow, and the UI stack:

```bash
python3 -m py_compile workbench/*.py tools/*.py examples/audio_conversion/run.py tests/*.py
.research-env/bin/python3 -m unittest discover -s tests -v
```

The first command matches CI (`.github/workflows/ci.yml`, Python 3.13) and compiles `tests/*.py`, unlike the command documented in AGENTS.md. CI installs `requirements-lab.txt` and runs both under a normal interpreter.

Linting is `ruff check .`, configured in `ruff.toml`. The tree is currently clean. Ruff is **not** part of CI, so run it before finishing work that touches Python.

Ruff is installed as a standalone binary at `~/.local/bin/ruff` — it is a Rust executable and needs no Python environment, which is how it works here despite the missing `pip`. To upgrade or reinstall it:

```bash
curl -sLO https://github.com/astral-sh/ruff/releases/latest/download/ruff-x86_64-unknown-linux-gnu.tar.gz
curl -sLO https://github.com/astral-sh/ruff/releases/latest/download/ruff-x86_64-unknown-linux-gnu.tar.gz.sha256
sha256sum -c ruff-x86_64-unknown-linux-gnu.tar.gz.sha256
tar xzf ruff-x86_64-unknown-linux-gnu.tar.gz
install -m 755 ruff-x86_64-unknown-linux-gnu/ruff ~/.local/bin/ruff
```

`RUF001`–`RUF003` are disabled on purpose: user-facing strings are Russian, and Cyrillic letters that resemble Latin ones are intended, not homoglyph errors. `E402` is ignored for `tools/`, `tests/`, `ui/`, and `examples/`, which insert the repository root on `sys.path` before importing `workbench`.

## Dependencies

Three layers, three files: `requirements-envelope.txt` is `jsonschema` alone; `requirements-lab.txt` adds PyYAML for the chain runner (CI installs this one); `requirements-ui.txt` adds FastAPI, Jinja2, and uvicorn for the local shell.

`mlflow` and the `opentelemetry-*` packages are **optional** — imported under `try/except`, present only in `.research-env`. PyYAML is imported lazily inside `workbench.experiment.read_yaml` for the same reason, so the core stays importable without it. Tests and the active core must stay runnable offline.

The local shell needs no `python-multipart`: `ui/app.py` parses its urlencoded form by hand.

`tools/run_chain.py` must also be launched with `.research-env/bin/python3` — it reads YAML. The shell's launch button is safe either way, because it spawns `sys.executable`, which is already the venv when uvicorn runs there.

The project is not installable; `tools/*.py` and `examples/audio_conversion/run.py` rely on `sys.path.insert(0, ROOT)`, so run them from the repository root.

## Project invariants

- **Unknown measurements stay absent or `null`.** Never coerce a missing value to zero (ADR 0004).
- **No universal score, no inferred verdict.** There is no generic total across evaluation dimensions, and a verdict is never derived from a score unless the policy declares the rule. `CODE`, `HUMAN`, and `LLM_JUDGE` evidence must stay distinguishable.
- **Schema changes are two-layer.** `schemas/execution-envelope-v1.schema.json` and the hand-written semantic checks in `validate_envelope` (`workbench/envelope.py` — unique IDs, unknown/self stage deps, DAG cycles, unknown observation and evaluation references, dimension scale bounds) must be kept in sync. Keep v1 backward-compatible.
- **Artifact paths are bundle-relative** and are rejected if they resolve outside `bundle_root`.
- Directory digests are `sha256-tree-manifest-v1`: a hash over sorted `sha256  size  relpath` lines, not a tarball hash.

## Experiment format

Implemented and documented on one page: `docs/design/stage-1.md`. One short YAML per experiment under `experiments/`, run by `tools/run_chain.py`, producing one execution envelope per candidate.

**Order of work (ADR 0006): a real run first, then the field.** A new field is added when a run actually needed it — not because a hypothetical scenario might. The old requirement that a gap appear in *both* a coding and a domain-neutral scenario is retired; it had turned into a driver of universality. The audio example is now a smoke test, not a reference scenario.

The superseded `docs/design/stage-1/` drafts (678 lines, 48 open questions) are kept only as discussion history; do not extend or cite them.

## ADRs

`docs/decisions/NNNN-slug.md`, numbered sequentially (0003–0006 here; 0001–0002 are under `archive/prototype-r4.2/docs/decisions/`). Each has a status line with a date, then Context / Decision / Consequences sections. The language shifted with 0005: 0003–0004 use `Status:` + `## Context / ## Decision / ## Consequences`, 0005–0006 use `Статус:` + `## Контекст / ## Решение / ## Следствия`. Follow 0006 for new ADRs.

0005 is accepted as a direction with implementation deferred; 0006 reverses part of the archived 0001 and is implemented.

## Git

Work lands as direct commits to `main` — do not open branches or PRs unless asked. Subjects are English, imperative, capitalized, no trailing period, no scope prefixes or issue refs, 3–5 words (`Separate historical benchmark`, `Record portable research bundle decision`).

## Language

Code, docstrings, commit messages, and this file are English. User-facing discussion and new explanatory documentation are Russian, using terms from `docs/GLOSSARY.ru.md`. `VISION.md`, `README.ru.md`, `docs/CURRENT_STATE.md`, `docs/envelope-v1.md`, `docs/design/stage-1.md`, and the local shell's templates are Russian; `README.md` and `AGENTS.md` are English.

## Scope boundaries

The project deliberately does not build its own trace store, trace viewer, prompt management, cost dashboard, human-labeling system, or execution engine (`VISION.md`). It reuses MLflow for experiment records and OpenTelemetry/OTLP for trace transport. The only owned contract is the versioned execution envelope (карточка исполнения).

Generated data never enters git: `executions/`, `agent_runs/`, `mlruns/`, `transfer-kit/`, `.research-env/`, `.promptfoo-*`, `.env*`. Examples write outside the repository (`/tmp` by convention).

---
name: validate
description: Run the repository's full local validation — byte-compile every Python file CI compiles, then run the offline unittest suite. Use before committing, after editing anything under workbench/, tools/, examples/, or tests/, or when asked to check that the active core still works.
---

Run the same two gates CI runs (`.github/workflows/ci.yml`, job `validate`, Python 3.13). From the repository root:

```bash
python3 -m py_compile workbench/*.py tools/*.py examples/audio_conversion/run.py tests/*.py
.research-env/bin/python3 -m unittest discover -s tests -v
```

Note that this compiles `tests/*.py`, which the command documented in `AGENTS.md` omits but CI includes. Use this version so local results match CI.

**Run the tests with `.research-env/bin/python3`, not the system `python3`.** The system interpreter has no `pip`, no `jsonschema`, and no PyYAML, so `unittest` fails with seven import errors that mean nothing about the code. Do not try to `pip install` anything — there is no pip. If `.research-env` is missing, say so and stop rather than reporting the import errors as test failures.

The UI modules are compiled separately, since they need the venv's FastAPI:

```bash
.research-env/bin/python3 -m py_compile ui/*.py
```

Then, **if `ruff` is available** (`command -v ruff`), also run it — it is configured in `ruff.toml` but is not part of CI, and it is not installed on every machine:

```bash
ruff check .
```

If ruff is not installed, say so in one line and move on; do not try to install it (the system Python has no `pip`).

Do not install or require `mlflow` or `opentelemetry-*` to make these pass — they are optional, guarded by `try/except`, and live in the untracked `.research-env` venv. Tests must stay offline. If a test failure traces back to a missing optional package, that is a bug in the test, not a missing dependency.

Report the outcome plainly: the exact failing test names and their output if anything fails, or a one-line confirmation if both gates pass.

## When changes are documentation-only

If the diff touches only Markdown under `docs/` and no schemas, code, or embedded code snippets, these gates are not meaningful — say so instead of running them. Run them if `schemas/`, `workbench/`, `tools/`, `examples/`, or `tests/` changed, or if a documented example command or JSON snippet was edited.

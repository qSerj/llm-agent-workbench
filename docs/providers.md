# Provider Setup

The runner generates a temporary `opencode.json` inside each task workspace.
It stores provider metadata and environment-variable references, never the
secret value itself. `providers.example.json` contains non-secret examples.

## OpenRouter

OpenRouter is a built-in OpenCode provider. Authenticate once through
OpenCode's `/connect` flow, select OpenRouter, and keep credentials in
OpenCode's own credential store. Pass the OpenRouter model ID without adding an
extra `openrouter/` prefix:

```bash
python3 run_agent.py \
  --provider openrouter \
  --model qwen/qwen3-coder \
  --tasks 1 \
  --tag openrouter
```

Free variants use their normal `:free` suffix. Prefer a specific free model to
`openrouter/free` for comparisons because the router may select different
models between runs.

## LM Studio

The runner can load and unload a local model through the `lms` CLI. Its default
OpenAI-compatible endpoint is `http://127.0.0.1:1234/v1`:

```bash
python3 run_agent.py \
  --provider lmstudio \
  --model openai/gpt-oss-20b \
  --gpu 0.5 \
  --context 32768 \
  --tasks 1,2,3 \
  --tag local
```

Use `--gpu off` for CPU-only execution, `--keep-loaded` to leave the benchmark
instance loaded, or `--skip-load` if the endpoint is already managed outside
the runner. `--gpu` and `--context` apply only to LM Studio.

## OpenAI-compatible endpoints

Use `compatible` for local proxies or hosted services that implement the
OpenAI API shape:

```bash
export MY_PROVIDER_KEY='replace-me'

python3 run_agent.py \
  --provider compatible \
  --provider-id myprovider \
  --provider-name "My provider" \
  --base-url https://example.invalid/v1 \
  --api-key-env MY_PROVIDER_KEY \
  --model exact-model-id \
  --tasks 1
```

`--api-key-env` is the *name* of an environment variable. The generated config
contains `{env:MY_PROVIDER_KEY}`, not its value. Omit the option if the endpoint
does not require client bearer authentication.

Optional `--provider-context` and `--provider-output` values describe limits to
OpenCode; they do not reconfigure the server-side model.

### gpt2giga

The usual local gpt2giga address is `http://localhost:8090`, making the API base
URL `http://127.0.0.1:8090/v1`:

```bash
python3 run_agent.py \
  --provider compatible \
  --provider-id giga \
  --provider-name "GigaChat via gpt2giga" \
  --base-url http://127.0.0.1:8090/v1 \
  --model GigaChat-3-Ultra \
  --tasks 1
```

Use the exact model and client-auth settings enabled by the local gpt2giga
instance. Credentials that gpt2giga itself uses to reach upstream services
belong to that process, not to this repository.

## Local energy estimates

For local runs, supply an observed or assumed average whole-PC power draw:

```bash
python3 run_agent.py \
  --provider lmstudio \
  --model openai/gpt-oss-20b \
  --tasks 1 \
  --power-watts 180 \
  --electricity-rate 6.5 \
  --electricity-currency RUB
```

The runner estimates kWh from wall time. It does not read a power meter and
does not attribute energy to individual tool calls.

## Security checklist

- Never place a real key in `providers.example.json`, a command committed to
  documentation, a result artifact, or `opencode.json`.
- Prefer provider credential stores or environment variables.
- Inspect a run before sharing it: raw traces and workspaces may contain source
  code, prompts, model output, environment-derived paths, or other sensitive
  material.
- Treat any cloud provider as a data boundary. Do not send proprietary inputs
  unless that use is explicitly approved.

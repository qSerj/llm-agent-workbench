"""Run a multi-stage candidate through OpenCode and record an execution envelope.

A candidate is an ordered list of stages. Every stage receives the workspace the
previous stage left behind, may edit only the files it declares, and contributes
its own measurements. Time, tokens, and money are attributed per stage, never
merged into a single total that hides where the budget went.

Unknown measurements stay ``None``. A provider that reports no cost produces a
``null`` observation, never a zero.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from workbench.envelope import directory_artifact, file_artifact

CHAIN_VERSION = "chain-v1"
LM_STUDIO_INSTANCE = "workbench-chain-current"
WORKSPACE_EXCLUSIONS = frozenset({".git", "bin", "obj"})

MEDIA_TYPES = {
    ".diff": "text/x-diff",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


@dataclass
class StageSpec:
    """One step of a candidate: a model, a prompt, and what it may edit."""

    role: str
    model: str
    prompt: Path
    allow_edit: list[str]
    provider: str = "openrouter"
    base_url: str | None = None
    api_key_env: str | None = None


@dataclass
class StageResult:
    stage_id: str
    spec: StageSpec
    directory: Path
    workspace: Path
    model_name: str
    exit_code: int
    wall_seconds: float
    usage: dict[str, Any] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix, "application/octet-stream")


def run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    process = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and process.returncode != 0:
        raise RuntimeError(f"command failed ({process.returncode}): {' '.join(args)}")
    return process


def opencode_version(executable: str = "opencode") -> str:
    try:
        process = subprocess.run(
            [executable, "--version"], text=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return process.stdout.strip() or "unknown"


def permission_config(allow_edit: list[str]) -> dict[str, Any]:
    """Deny every edit except the exact relative paths this stage declares."""
    if not allow_edit:
        raise ValueError("a stage must declare at least one editable path")
    for path in allow_edit:
        parsed = Path(path)
        if parsed.is_absolute() or ".." in parsed.parts or set("*?[]") & set(path):
            raise ValueError(f"allow_edit must be an exact relative path: {path}")
    return {
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "lsp": "allow",
        "edit": {"*": "deny", **{path: "allow" for path in allow_edit}},
        "bash": {
            "*": "deny",
            "git status*": "allow",
            "git diff*": "allow",
            "dotnet build*": "allow",
            "dotnet test*": "allow",
        },
        "webfetch": "deny",
        "websearch": "deny",
    }


def run_directory(output: Path, experiment_id: str, today: str) -> Path:
    """Group a run by the day it happened, so a repeat never overwrites a result.

    ``run_candidate`` refuses to write over an existing directory on purpose, so
    a second run on the same day gets a numbered suffix instead of colliding.
    """
    base = output / experiment_id / today
    if not base.exists():
        return base
    attempt = 2
    while (candidate := base.with_name(f"{today}-{attempt}")).exists():
        attempt += 1
    return candidate


def build_opencode_config(
    spec: StageSpec, permission: dict[str, Any] | None = None
) -> tuple[dict[str, Any], str]:
    """Return the OpenCode configuration and the model name it should run.

    A stage must declare what it may edit. A caller that is not running a stage —
    asking a model for a draft, say — passes its own permissions instead, and
    ``allow_edit`` is then not consulted at all.
    """
    config: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "permission": permission or permission_config(spec.allow_edit),
    }

    if spec.provider == "openrouter":
        model_name = f"openrouter/{spec.model}"
        config["model"] = model_name
        return config, model_name

    if spec.provider == "lmstudio":
        options: dict[str, Any] = {
            "baseURL": spec.base_url or "http://127.0.0.1:1234/v1"
        }
        config["provider"] = {
            "lmstudio": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "LM Studio local workbench",
                "options": options,
                "models": {LM_STUDIO_INSTANCE: {"name": spec.model}},
            }
        }
        model_name = f"lmstudio/{LM_STUDIO_INSTANCE}"
        config["model"] = model_name
        return config, model_name

    if spec.provider == "compatible":
        if not spec.base_url:
            raise ValueError("provider 'compatible' requires base_url")
        options = {"baseURL": spec.base_url}
        if spec.api_key_env:
            options["apiKey"] = "{env:" + spec.api_key_env + "}"
        config["provider"] = {
            "compatible": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "compatible endpoint",
                "options": options,
                "models": {spec.model: {"name": spec.model}},
            }
        }
        model_name = f"compatible/{spec.model}"
        config["model"] = model_name
        return config, model_name

    raise ValueError(f"unknown provider: {spec.provider}")


def collect_usage_from_jsonl(path: Path) -> dict[str, Any]:
    """Summarise OpenCode events without guessing anything the provider omitted.

    OpenCode reports ``part.cost`` on ``step_finish`` for providers that publish
    it. Those values are per-step charges, so they are summed. A provider that
    reports nothing leaves ``api_cost_usd`` as ``None``.
    """
    tool_calls = 0
    failed_tool_calls = 0
    step_finishes = 0
    token_steps = 0
    totals = {"input": 0, "output": 0, "reasoning": 0, "total": 0}
    step_costs: list[float] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        part = event.get("part") or {}

        if kind == "tool_use":
            tool_calls += 1
            if (part.get("state") or {}).get("status") in {"error", "failed"}:
                failed_tool_calls += 1
        elif kind == "step_finish":
            step_finishes += 1
            tokens = part.get("tokens")
            if isinstance(tokens, dict):
                token_steps += 1
                for key in totals:
                    value = tokens.get(key)
                    if isinstance(value, (int, float)):
                        totals[key] += value
            cost = part.get("cost")
            if isinstance(cost, (int, float)):
                step_costs.append(float(cost))

    return {
        "tool_calls": tool_calls,
        "failed_tool_calls": failed_tool_calls,
        "step_finishes": step_finishes,
        "tokens": dict(totals) if token_steps else None,
        "api_cost_usd": round(sum(step_costs), 12) if step_costs else None,
        "cost_reporting_steps": len(step_costs),
    }


def stream_opencode(
    args: list[str], cwd: Path, log_path: Path, heartbeat: int = 30
) -> tuple[int, float]:
    """Run OpenCode, mirror its event stream to a log, and report wall time."""
    print("$", " ".join(args), flush=True)
    process = subprocess.Popen(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    lines: queue.Queue = queue.Queue()
    sentinel = object()

    def reader() -> None:
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(sentinel)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    started = time.monotonic()
    last_event = started
    next_heartbeat = started + heartbeat if heartbeat > 0 else float("inf")

    with log_path.open("w", encoding="utf-8") as log:
        while True:
            now = time.monotonic()
            try:
                item = lines.get(timeout=max(0.1, min(1.0, next_heartbeat - now)))
            except queue.Empty:
                item = None
            if item is sentinel:
                break
            if isinstance(item, str):
                log.write(item)
                log.flush()
                if item.strip():
                    last_event = time.monotonic()
            now = time.monotonic()
            if heartbeat > 0 and now >= next_heartbeat:
                quiet = int(now - last_event)
                elapsed = int(now - started)
                print(
                    f"[{elapsed // 60:02d}:{elapsed % 60:02d}] still running — "
                    f"last OpenCode output {quiet}s ago",
                    flush=True,
                )
                next_heartbeat = now + heartbeat

    exit_code = process.wait()
    thread.join(timeout=1)
    return exit_code, time.monotonic() - started


def run_stage(
    spec: StageSpec,
    index: int,
    source_workspace: Path,
    directory: Path,
    opencode: str = "opencode",
    heartbeat: int = 30,
) -> StageResult:
    """Copy the incoming workspace, run one stage over it, and record its trace."""
    directory.mkdir(parents=True)
    workspace = directory / "workspace"
    shutil.copytree(
        source_workspace, workspace, ignore=shutil.ignore_patterns(".git")
    )

    config, model_name = build_opencode_config(spec)
    (workspace / "opencode.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    prompt = spec.prompt.read_text(encoding="utf-8")
    (directory / "prompt.md").write_text(prompt, encoding="utf-8")
    (directory / "effective_model.txt").write_text(model_name + "\n", encoding="utf-8")

    run(["git", "init", "-q"], cwd=workspace)
    run(["git", "config", "user.email", "workbench@example.invalid"], cwd=workspace)
    run(["git", "config", "user.name", "Workbench Chain"], cwd=workspace)
    run(["git", "add", "."], cwd=workspace)
    run(["git", "commit", "-q", "-m", "stage-input"], cwd=workspace)

    log_path = directory / "opencode.jsonl"
    exit_code, wall_seconds = stream_opencode(
        [
            opencode,
            "run",
            "--auto",
            "--format",
            "json",
            "--model",
            model_name,
            "--dir",
            str(workspace),
            prompt,
        ],
        cwd=workspace,
        log_path=log_path,
        heartbeat=heartbeat,
    )

    usage = collect_usage_from_jsonl(log_path)
    (directory / "exit.json").write_text(
        json.dumps(
            {"exit_code": exit_code, "wall_seconds": wall_seconds, **usage},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (directory / "git.diff").write_text(
        run(["git", "diff"], cwd=workspace, check=False).stdout, encoding="utf-8"
    )
    (directory / "git.status.txt").write_text(
        run(["git", "status", "--short"], cwd=workspace, check=False).stdout,
        encoding="utf-8",
    )

    return StageResult(
        stage_id=f"{index}-{spec.role.lower()}",
        spec=spec,
        directory=directory,
        workspace=workspace,
        model_name=model_name,
        exit_code=exit_code,
        wall_seconds=wall_seconds,
        usage=usage,
    )


def stage_observations(result: StageResult) -> list[dict[str, Any]]:
    """Per-stage measurements. Anything the provider withheld stays ``None``."""
    usage = result.usage
    tokens = usage.get("tokens") or {}
    observations = [
        {
            "name": "wall_time",
            "value": round(result.wall_seconds, 6),
            "unit": "s",
            "method": "runner monotonic clock around the OpenCode process",
            "stage_id": result.stage_id,
        },
        {
            "name": "tool_calls",
            "value": usage.get("tool_calls"),
            "unit": "calls",
            "method": "count of OpenCode tool_use events",
            "stage_id": result.stage_id,
        },
        {
            "name": "failed_tool_calls",
            "value": usage.get("failed_tool_calls"),
            "unit": "calls",
            "method": "OpenCode tool_use events with error or failed status",
            "stage_id": result.stage_id,
        },
        {
            "name": "api_cost",
            "value": usage.get("api_cost_usd"),
            "unit": "USD",
            "method": (
                "sum of explicit OpenCode step_finish costs; null when the "
                "provider reported none"
            ),
            "stage_id": result.stage_id,
        },
    ]
    for key in ("input", "output", "reasoning", "total"):
        observations.append(
            {
                "name": f"{key}_tokens",
                "value": tokens.get(key),
                "unit": "tokens",
                "method": "sum of provider-reported step token counts",
                "stage_id": result.stage_id,
            }
        )
    return observations


def total_cost(results: list[StageResult]) -> float | None:
    """Total cost, or ``None`` when any stage withheld its own cost.

    A partial sum presented as a total would understate the price of the
    candidate, so an incomplete chain reports unknown rather than a number.
    """
    costs = [result.usage.get("api_cost_usd") for result in results]
    if any(cost is None for cost in costs):
        return None
    return round(sum(costs), 12)


def build_envelope(
    experiment_id: str,
    candidate_id: str,
    task: dict[str, str],
    case: dict[str, str],
    results: list[StageResult],
    bundle_root: Path,
    source_workspace: Path,
    repetition: int,
    started_at: str,
    finished_at: str,
    opencode: str = "opencode",
) -> dict[str, Any]:
    """Assemble one execution envelope describing the whole candidate."""
    artifacts: list[dict[str, Any]] = [
        directory_artifact(
            "input-workspace",
            "INPUT",
            source_workspace,
            bundle_root,
            "inode/directory",
            WORKSPACE_EXCLUSIONS,
        )
    ]
    stages: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    execution_id = f"{experiment_id}--{candidate_id}--r{repetition}"

    previous_output = "input-workspace"
    for position, result in enumerate(results):
        workspace_id = f"{result.stage_id}-workspace"
        artifacts.append(
            directory_artifact(
                workspace_id,
                "OUTPUT",
                result.workspace,
                bundle_root,
                "inode/directory",
                WORKSPACE_EXCLUSIONS,
            )
        )
        for name in ("prompt.md", "opencode.jsonl", "git.diff", "exit.json"):
            path = result.directory / name
            if not path.is_file():
                continue
            role = "INPUT" if name == "prompt.md" else "LOG"
            artifacts.append(
                file_artifact(
                    f"{result.stage_id}-{name.replace('.', '-')}",
                    role,
                    path,
                    bundle_root,
                    media_type_for(path),
                )
            )
        stages.append(
            {
                "id": result.stage_id,
                "role": result.spec.role,
                "execution_id": f"{execution_id}::{result.stage_id}",
                "depends_on": [results[position - 1].stage_id] if position else [],
                "input_artifact_ids": [previous_output],
                "output_artifact_ids": [workspace_id],
            }
        )
        observations.extend(stage_observations(result))
        previous_output = workspace_id

    observations.append(
        {
            "name": "wall_time",
            "value": round(sum(item.wall_seconds for item in results), 6),
            "unit": "s",
            "method": "sum of stage wall times",
        }
    )
    observations.append(
        {
            "name": "api_cost",
            "value": total_cost(results),
            "unit": "USD",
            "method": "sum of stage costs; null when any stage reported none",
        }
    )
    observations.append(
        {
            "name": "stage_count",
            "value": len(results),
            "unit": "stages",
            "method": "declared candidate stages",
        }
    )

    failed = [result for result in results if result.exit_code != 0]
    if not failed:
        status = "SUCCEEDED"
    elif len(failed) == len(results):
        status = "FAILED"
    else:
        status = "PARTIAL"

    return {
        "schema_version": "1.0",
        "execution_id": execution_id,
        "task": task,
        "case": case,
        "candidate": {
            "id": candidate_id,
            "version": "1",
            "parameters": {
                "stages": [
                    {"role": item.spec.role, "model": item.model_name}
                    for item in results
                ]
            },
        },
        "repetition": repetition,
        "lifecycle": {
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "timestamp_basis": "UTC system clock",
        },
        "executor": {
            "implementation": "workbench-chain-opencode",
            "version": f"{CHAIN_VERSION} opencode/{opencode_version(opencode)}",
            "exit_code": results[-1].exit_code if results else None,
        },
        "artifacts": artifacts,
        "observations": observations,
        "stages": stages,
        "evaluations": [],
        "correlations": [],
    }


def run_candidate(
    experiment_id: str,
    candidate_id: str,
    task: dict[str, str],
    case: dict[str, str],
    specs: list[StageSpec],
    source_workspace: Path,
    output_directory: Path,
    repetition: int = 1,
    opencode: str = "opencode",
    heartbeat: int = 30,
) -> dict[str, Any]:
    """Run every stage in order and return the resulting execution envelope."""
    if not specs:
        raise ValueError("a candidate needs at least one stage")
    if output_directory.exists():
        raise ValueError(f"output directory already exists: {output_directory}")
    output_directory.mkdir(parents=True)

    started_at = utc_now()
    results: list[StageResult] = []

    # The bundle must be self-contained: artifact paths are bundle-relative and
    # are rejected if they resolve outside it, so the input is copied in first.
    input_workspace = output_directory / "input-workspace"
    shutil.copytree(
        source_workspace, input_workspace, ignore=shutil.ignore_patterns(".git")
    )
    workspace = input_workspace

    for position, spec in enumerate(specs, start=1):
        print(f"\n=== {candidate_id}: этап {position}/{len(specs)} — {spec.role} ===")
        result = run_stage(
            spec,
            position,
            workspace,
            output_directory / "stages" / f"{position}-{spec.role.lower()}",
            opencode=opencode,
            heartbeat=heartbeat,
        )
        results.append(result)
        workspace = result.workspace
        if result.exit_code != 0:
            print(f"этап {result.stage_id} завершился с кодом {result.exit_code}")
            break

    return build_envelope(
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        task=task,
        case=case,
        results=results,
        bundle_root=output_directory,
        source_workspace=input_workspace,
        repetition=repetition,
        started_at=started_at,
        finished_at=utc_now(),
        opencode=opencode,
    )

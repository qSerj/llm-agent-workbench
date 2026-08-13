#!/usr/bin/env python3
"""Запустить один воспроизводимый этап OpenCode над копией рабочего пространства."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_agent import build_opencode_config, cmd, collect_usage_from_jsonl, stream_opencode


def restrict_edits(config: dict, allowed_paths: list[str]) -> None:
    if not allowed_paths:
        raise ValueError("at least one --allow-edit path is required")
    for path in allowed_paths:
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or any(character in path for character in "*?[]")
        ):
            raise ValueError(f"--allow-edit must be an exact relative path: {path}")
    config["permission"]["edit"] = {
        "*": "deny",
        **{path: "allow" for path in allowed_paths},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-workspace", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True, help="OpenRouter model ID without prefix")
    parser.add_argument(
        "--allow-edit",
        action="append",
        required=True,
        help="Exact workspace-relative file the stage may edit; repeat as needed",
    )
    parser.add_argument("--heartbeat", type=int, default=15)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    output.mkdir(parents=True)
    workspace = output / "workspace"
    shutil.copytree(
        args.source_workspace.resolve(),
        workspace,
        ignore=shutil.ignore_patterns(".git"),
    )

    provider_args = SimpleNamespace(
        provider="openrouter",
        model=args.model,
        base_url=None,
        provider_id=None,
        provider_name=None,
        api_key_env=None,
        provider_context=None,
        provider_output=None,
    )
    config, model_name = build_opencode_config(provider_args)
    restrict_edits(config, args.allow_edit)
    (workspace / "opencode.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    prompt = args.prompt.read_text(encoding="utf-8")
    (output / "prompt.md").write_text(prompt, encoding="utf-8")
    (output / "effective_model.txt").write_text(model_name + "\n", encoding="utf-8")

    cmd(["git", "init", "-q"], cwd=workspace)
    cmd(["git", "config", "user.email", "agent-bench@example.invalid"], cwd=workspace)
    cmd(["git", "config", "user.name", "Agent Bench"], cwd=workspace)
    cmd(["git", "add", "."], cwd=workspace)
    cmd(["git", "commit", "-q", "-m", "stage-input"], cwd=workspace)

    log_path = output / "opencode.jsonl"
    returncode, wall_seconds = stream_opencode(
        [
            "opencode",
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
        heartbeat=args.heartbeat,
    )
    usage = collect_usage_from_jsonl(log_path)
    result = {"returncode": returncode, "wall_seconds": wall_seconds, **usage}
    (output / "exit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "git.diff").write_text(
        cmd(["git", "diff"], cwd=workspace, check=False).stdout, encoding="utf-8"
    )
    (output / "git.status.txt").write_text(
        cmd(["git", "status", "--short"], cwd=workspace, check=False).stdout,
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LM_INSTANCE = "agent-bench-current"
VERSION = "2026-08-11-r4.2"


def elapsed(t0: float) -> str:
    sec = int(time.monotonic() - t0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def cmd(args, cwd=None, check=True, env=None, log=None):
    print("$", " ".join(map(str, args)), flush=True)
    p = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if log:
        Path(log).write_text(p.stdout, encoding="utf-8")
    elif p.stdout:
        print(p.stdout, end="" if p.stdout.endswith("\n") else "\n")
    if check and p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(map(str, args))}"
        )
    return p


def init_workspace(dst):
    shutil.copytree(ROOT / "fixture", dst)
    cmd(["git", "init", "-q"], cwd=dst)
    cmd(["git", "config", "user.email", "agent-bench@example.invalid"], cwd=dst)
    cmd(["git", "config", "user.name", "Agent Bench"], cwd=dst)
    cmd(["git", "add", "."], cwd=dst)
    cmd(["git", "commit", "-q", "-m", "baseline"], cwd=dst)


def permission_config():
    # OpenCode v1/current schema used by this benchmark.
    return {
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "lsp": "allow",
        "edit": {"*": "deny", "docs/*": "allow", "docs/**": "allow"},
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


def build_opencode_config(args):
    """
    Return (config, opencode_model_name).

    provider modes:
      lmstudio   -> local LM Studio, runner loads model itself
      openrouter -> OpenCode built-in OpenRouter provider/auth
      compatible -> arbitrary OpenAI-compatible endpoint
    """
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "permission": permission_config(),
    }

    if args.provider == "lmstudio":
        provider_id = "lmstudio"
        cfg["provider"] = {
            provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "LM Studio local benchmark",
                "options": {"baseURL": args.base_url or "http://127.0.0.1:1234/v1"},
                "models": {LM_INSTANCE: {"name": "LM Studio benchmark model"}},
            }
        }
        model_name = f"{provider_id}/{LM_INSTANCE}"

    elif args.provider == "openrouter":
        # OpenRouter is a built-in OpenCode provider. Credentials should be
        # configured outside the benchmark via /connect (or standard env auth).
        model_name = f"openrouter/{args.model}"
        cfg["model"] = model_name

    elif args.provider == "compatible":
        if not args.base_url:
            raise SystemExit("--provider compatible требует --base-url")
        provider_id = args.provider_id or "compatible"
        opts = {"baseURL": args.base_url}
        if args.api_key_env:
            opts["apiKey"] = "{env:" + args.api_key_env + "}"

        model_cfg = {"name": args.model}
        if args.provider_context:
            model_cfg["limit"] = {
                "context": args.provider_context,
                "output": args.provider_output or 4096,
            }
        elif args.provider_output:
            model_cfg["limit"] = {"output": args.provider_output}

        cfg["provider"] = {
            provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": args.provider_name or provider_id,
                "options": opts,
                "models": {args.model: model_cfg},
            }
        }
        model_name = f"{provider_id}/{args.model}"
        cfg["model"] = model_name

    else:
        raise SystemExit(f"Unknown provider: {args.provider}")

    return cfg, model_name


def write_config(ws, args):
    cfg, model_name = build_opencode_config(args)
    (ws / "opencode.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return model_name


def short_value(v, limit=100):
    if isinstance(v, str):
        s = v.replace("\n", " ")
        return s if len(s) <= limit else s[: limit - 1] + "…"
    if isinstance(v, (int, float, bool)) or v is None:
        return str(v)
    try:
        s = json.dumps(v, ensure_ascii=False)
    except Exception:
        s = str(v)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def describe_tool(part):
    tool = part.get("tool", "?")
    state = part.get("state") or {}
    inp = state.get("input") or {}
    status = state.get("status", "")
    interesting = []
    for k in ("filePath", "path", "pattern", "query", "include", "command", "content"):
        if k in inp:
            interesting.append(f"{k}={short_value(inp[k])}")
    if not interesting:
        for k, v in list(inp.items())[:3]:
            interesting.append(f"{k}={short_value(v)}")
    suffix = " | " + ", ".join(interesting) if interesting else ""
    return f"TOOL {tool} [{status}]{suffix}"


def describe_event(obj):
    et = obj.get("type", "")
    part = obj.get("part") or {}

    if et == "tool_use":
        return describe_tool(part)
    if et == "step_start":
        return "model step started"
    if et == "step_finish":
        tok = part.get("tokens") or {}
        reason = part.get("reason")
        pieces = []
        if reason:
            pieces.append(f"reason={reason}")
        if tok:
            pieces.append(
                "tokens="
                f"{tok.get('total', '?')} total / "
                f"{tok.get('input', '?')} in / "
                f"{tok.get('output', '?')} out / "
                f"{tok.get('reasoning', '?')} reasoning"
            )
        if isinstance(part.get("cost"), (int, float)):
            pieces.append(f"cost={part['cost']}")
        return "STEP finished" + (": " + "; ".join(pieces) if pieces else "")
    if et == "text":
        txt = part.get("text", "")
        if not txt:
            return "TEXT event"
        first = next((x.strip() for x in txt.splitlines() if x.strip()), "")
        return "TEXT " + short_value(first, 140)
    return None


def collect_usage_from_jsonl(path):
    """
    Best-effort usage summary from OpenCode JSON events.

    OpenCode emits `part.cost` on step_finish for providers that report cost.
    In the observed OpenRouter logs these are per-step charges (not cumulative),
    so r4 sums them into `total_reported_cost_usd`.

    If a provider omits cost entirely (typical for local endpoints and possibly
    some proxies), total_reported_cost_usd remains None rather than guessing.
    """
    tool_calls = 0
    failed_tool_calls = 0
    step_finishes = 0
    last_tokens = None
    step_costs = []

    total_input = 0
    total_output = 0
    total_reasoning = 0
    total_tokens = 0
    token_steps = 0

    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        et = obj.get("type")
        part = obj.get("part") or {}

        if et == "tool_use":
            tool_calls += 1
            status = (part.get("state") or {}).get("status")
            if status in {"error", "failed"}:
                failed_tool_calls += 1

        elif et == "step_finish":
            step_finishes += 1

            tok = part.get("tokens")
            if isinstance(tok, dict):
                last_tokens = tok
                token_steps += 1
                for key, target in (
                    ("input", "input"),
                    ("output", "output"),
                    ("reasoning", "reasoning"),
                    ("total", "total"),
                ):
                    value = tok.get(key)
                    if isinstance(value, (int, float)):
                        if target == "input":
                            total_input += value
                        elif target == "output":
                            total_output += value
                        elif target == "reasoning":
                            total_reasoning += value
                        elif target == "total":
                            total_tokens += value

            cost = part.get("cost")
            if isinstance(cost, (int, float)):
                step_costs.append(float(cost))

    total_cost = round(sum(step_costs), 12) if step_costs else None

    return {
        "tool_calls": tool_calls,
        "failed_tool_calls": failed_tool_calls,
        "step_finishes": step_finishes,
        "last_reported_tokens": last_tokens,
        "token_reporting_steps": token_steps,
        "summed_step_tokens": {
            "input": total_input,
            "output": total_output,
            "reasoning": total_reasoning,
            "total": total_tokens,
        } if token_steps else None,
        "reported_step_costs_usd": step_costs,
        "total_reported_cost_usd": total_cost,
        "cost_reporting_steps": len(step_costs),
        "cost_is_estimate": False if step_costs else None,
        "cost_note": (
            "Sum of explicit OpenCode step_finish part.cost values; no tariff guessing."
            if step_costs
            else "Provider/OpenCode emitted no explicit step cost."
        ),
    }


def stream_opencode(args, cwd, log_path, heartbeat=30, verbose_events=False):
    print("$", " ".join(map(str, args)), flush=True)
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    q = queue.Queue()
    sentinel = object()

    def reader():
        try:
            for line in proc.stdout:
                q.put(line)
        finally:
            q.put(sentinel)

    th = threading.Thread(target=reader, daemon=True)
    th.start()

    t0 = time.monotonic()
    last_event = t0
    next_heartbeat = t0 + heartbeat if heartbeat > 0 else float("inf")

    with Path(log_path).open("w", encoding="utf-8") as log:
        done = False
        while not done:
            now = time.monotonic()
            timeout = max(0.1, min(1.0, next_heartbeat - now))
            try:
                item = q.get(timeout=timeout)
            except queue.Empty:
                item = None

            if item is sentinel:
                done = True
                continue

            if isinstance(item, str):
                log.write(item)
                log.flush()
                stripped = item.strip()
                if stripped:
                    last_event = time.monotonic()
                    if verbose_events:
                        print(f"[{elapsed(t0)}] RAW {stripped}", flush=True)
                    else:
                        try:
                            obj = json.loads(stripped)
                        except json.JSONDecodeError:
                            if stripped.startswith("["):
                                print(
                                    f"[{elapsed(t0)}] {short_value(stripped, 180)}",
                                    flush=True,
                                )
                        else:
                            msg = describe_event(obj)
                            if msg:
                                print(f"[{elapsed(t0)}] {msg}", flush=True)

            now = time.monotonic()
            if heartbeat > 0 and now >= next_heartbeat:
                quiet = int(now - last_event)
                print(
                    f"[{elapsed(t0)}] still running — "
                    f"last OpenCode output {quiet}s ago",
                    flush=True,
                )
                next_heartbeat = now + heartbeat

    rc = proc.wait()
    th.join(timeout=1)
    wall = time.monotonic() - t0
    print(f"[{elapsed(t0)}] OpenCode finished, rc={rc}", flush=True)
    return rc, wall


def main():
    ap = argparse.ArgumentParser(
        description="Provider-agnostic OpenCode agent benchmark"
    )
    ap.add_argument("--version", action="store_true")
    ap.add_argument(
        "--provider",
        choices=["lmstudio", "openrouter", "compatible"],
        default="lmstudio",
    )
    ap.add_argument("--model", help="Provider model ID")
    ap.add_argument("--tag", default="")
    ap.add_argument("--tasks", default="1,2,3")
    ap.add_argument("--opencode", default="opencode")
    ap.add_argument("--heartbeat", type=int, default=30)
    ap.add_argument("--verbose-events", action="store_true")
    ap.add_argument(
        "--power-watts",
        type=float,
        help=(
            "Average whole-PC power draw during the run, in watts. "
            "Used only to estimate local energy consumption."
        ),
    )
    ap.add_argument(
        "--electricity-rate",
        type=float,
        help=(
            "Optional electricity price per kWh. Used with --power-watts "
            "to estimate energy cost."
        ),
    )
    ap.add_argument(
        "--electricity-currency",
        default="",
        help="Optional currency label for --electricity-rate, e.g. EUR, RUB, USD.",
    )

    # LM Studio only
    ap.add_argument("--gpu", default="0.5")
    ap.add_argument("--context", type=int, default=32768)
    ap.add_argument("--keep-loaded", action="store_true")
    ap.add_argument("--skip-load", action="store_true")

    # Custom OpenAI-compatible only (also usable for local proxies such as gpt2giga)
    ap.add_argument("--base-url")
    ap.add_argument("--provider-id")
    ap.add_argument("--provider-name")
    ap.add_argument(
        "--api-key-env",
        help="Name of env variable holding API key; key itself is never written",
    )
    ap.add_argument("--provider-context", type=int)
    ap.add_argument("--provider-output", type=int)

    a = ap.parse_args()

    if a.version:
        print(VERSION)
        return
    if not a.model:
        raise SystemExit("Нужен --model MODEL")
    if a.power_watts is not None and a.power_watts < 0:
        raise SystemExit("--power-watts не может быть отрицательным")
    if a.electricity_rate is not None and a.electricity_rate < 0:
        raise SystemExit("--electricity-rate не может быть отрицательным")
    if a.electricity_rate is not None and a.power_watts is None:
        raise SystemExit("--electricity-rate имеет смысл только вместе с --power-watts")
    if not shutil.which(a.opencode):
        raise SystemExit(f"Не найден {a.opencode} в PATH")
    if a.provider == "lmstudio" and not a.skip_load and not shutil.which("lms"):
        raise SystemExit("Не найден lms в PATH")

    selected = [int(x) for x in a.tasks.split(",") if x.strip()]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = lambda s: "".join(c if c.isalnum() or c in "-_." else "_" for c in s)
    provider_label = a.provider_id if a.provider == "compatible" and a.provider_id else a.provider
    run_name = f"{stamp}_{safe(provider_label)}_{safe(a.model)}"
    if a.tag:
        run_name += f"_{safe(a.tag)}"
    run = ROOT / "agent_runs" / run_name
    run.mkdir(parents=True, exist_ok=True)

    meta = {
        "runner_version": VERSION,
        "timestamp": stamp,
        "provider": a.provider,
        "provider_id": a.provider_id,
        "provider_name": a.provider_name,
        "model": a.model,
        "base_url": a.base_url,
        "api_key_env": a.api_key_env,
        "gpu": a.gpu if a.provider == "lmstudio" else None,
        "context": a.context if a.provider == "lmstudio" else a.provider_context,
        "provider_output": a.provider_output,
        "tasks": selected,
        "tag": a.tag,
        "heartbeat_seconds": a.heartbeat,
        "power_watts": a.power_watts,
        "electricity_rate_per_kwh": a.electricity_rate,
        "electricity_currency": a.electricity_currency or None,
    }
    (run / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    loaded = False
    run_task_summaries = []
    try:
        if a.provider == "lmstudio" and not a.skip_load:
            cmd(["lms", "unload", "--all"], check=False)
            cmd(
                [
                    "lms", "load", a.model,
                    "--gpu", str(a.gpu),
                    "--context-length", str(a.context),
                    "--identifier", LM_INSTANCE,
                ]
            )
            loaded = True

        for n in selected:
            tfile = ROOT / "tasks" / f"{n:02d}.md"
            if not tfile.exists():
                raise RuntimeError(f"missing task {n}")

            td = run / f"task{n:02d}"
            td.mkdir()
            ws = td / "workspace"
            init_workspace(ws)
            model_name = write_config(ws, a)

            prompt = tfile.read_text(encoding="utf-8")
            (td / "prompt.md").write_text(prompt, encoding="utf-8")
            (td / "effective_model.txt").write_text(model_name + "\n", encoding="utf-8")

            print("\n" + "=" * 76, flush=True)
            print(f"TASK {n} | provider={provider_label} | model={a.model}", flush=True)
            print(f"OpenCode model: {model_name}", flush=True)
            print(f"Workspace: {ws}", flush=True)
            print("=" * 76, flush=True)

            log_path = td / "opencode.jsonl"
            oc_args = [
                a.opencode,
                "run",
                "--auto",
                "--format", "json",
                "--model", model_name,
                "--dir", str(ws),
                prompt,
            ]
            rc, wall = stream_opencode(
                oc_args,
                cwd=ws,
                log_path=log_path,
                heartbeat=a.heartbeat,
                verbose_events=a.verbose_events,
            )

            usage = collect_usage_from_jsonl(log_path)

            estimated_kwh = (
                (a.power_watts * wall) / 3_600_000.0
                if a.power_watts is not None
                else None
            )
            estimated_electricity_cost = (
                estimated_kwh * a.electricity_rate
                if estimated_kwh is not None and a.electricity_rate is not None
                else None
            )

            exit_info = {
                "returncode": rc,
                "wall_seconds": wall,
                "power_watts_assumed": a.power_watts,
                "estimated_kwh": estimated_kwh,
                "electricity_rate_per_kwh": a.electricity_rate,
                "electricity_currency": a.electricity_currency or None,
                "estimated_electricity_cost": estimated_electricity_cost,
                **usage,
            }
            (td / "exit.json").write_text(
                json.dumps(exit_info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            run_task_summaries.append({
                "task": n,
                "returncode": rc,
                "wall_seconds": wall,
                "tool_calls": usage["tool_calls"],
                "failed_tool_calls": usage["failed_tool_calls"],
                "total_reported_cost_usd": usage["total_reported_cost_usd"],
                "summed_step_tokens": usage["summed_step_tokens"],
                "power_watts_assumed": a.power_watts,
                "estimated_kwh": estimated_kwh,
                "estimated_electricity_cost": estimated_electricity_cost,
            })

            diff = cmd(["git", "diff"], cwd=ws, check=False).stdout
            (td / "git.diff").write_text(diff, encoding="utf-8")
            status = cmd(["git", "status", "--short"], cwd=ws, check=False).stdout
            (td / "git.status.txt").write_text(status, encoding="utf-8")

            gp = cmd(
                [sys.executable, str(ROOT / "grade.py"), str(ws), "--task", str(n)],
                check=False,
            )
            (td / "grade.json").write_text(gp.stdout, encoding="utf-8")

            cost_text = (
                f", cost=${usage['total_reported_cost_usd']:.6f}"
                if usage["total_reported_cost_usd"] is not None
                else ", cost=n/a"
            )
            energy_text = (
                f", energy≈{estimated_kwh:.4f} kWh"
                if estimated_kwh is not None
                else ""
            )
            electricity_text = ""
            if estimated_electricity_cost is not None:
                cur = (a.electricity_currency + " ") if a.electricity_currency else ""
                electricity_text = (
                    f", electricity≈{cur}{estimated_electricity_cost:.4f}"
                )
            print(
                f"\nTask {n} complete: rc={rc}, wall={wall:.1f}s, "
                f"tool_calls={usage['tool_calls']}, "
                f"failed_tools={usage['failed_tool_calls']}"
                f"{cost_text}{energy_text}{electricity_text}",
                flush=True,
            )

    finally:
        if loaded and not a.keep_loaded:
            cmd(["lms", "unload", "--all"], check=False)

    known_costs = [
        x["total_reported_cost_usd"]
        for x in run_task_summaries
        if x["total_reported_cost_usd"] is not None
    ]
    all_tasks_have_cost = (
        bool(run_task_summaries)
        and len(known_costs) == len(run_task_summaries)
    )
    run_summary = {
        "provider": a.provider,
        "provider_id": a.provider_id,
        "model": a.model,
        "tasks": run_task_summaries,
        "total_wall_seconds": sum(x["wall_seconds"] for x in run_task_summaries),
        "total_tool_calls": sum(x["tool_calls"] for x in run_task_summaries),
        "total_failed_tool_calls": sum(
            x["failed_tool_calls"] for x in run_task_summaries
        ),
        "total_reported_cost_usd": (
            round(sum(known_costs), 12) if known_costs else None
        ),
        "all_tasks_reported_cost": all_tasks_have_cost,
        "power_watts_assumed": a.power_watts,
        "estimated_kwh": (
            sum(
                x["estimated_kwh"]
                for x in run_task_summaries
                if x["estimated_kwh"] is not None
            )
            if a.power_watts is not None
            else None
        ),
        "electricity_rate_per_kwh": a.electricity_rate,
        "electricity_currency": a.electricity_currency or None,
        "estimated_electricity_cost": (
            sum(
                x["estimated_electricity_cost"]
                for x in run_task_summaries
                if x["estimated_electricity_cost"] is not None
            )
            if a.power_watts is not None and a.electricity_rate is not None
            else None
        ),
        "cost_note": (
            "Total is a sum of explicit OpenCode per-step cost events."
            if known_costs
            else "No explicit provider cost events were available."
        ),
    }
    (run / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\\n" + "=" * 76)
    print("RUN SUMMARY")
    print(f"wall: {run_summary['total_wall_seconds']:.1f}s")
    print(f"tool calls: {run_summary['total_tool_calls']}")
    if run_summary["total_reported_cost_usd"] is not None:
        partial = "" if all_tasks_have_cost else " (partial: some tasks had no cost)"
        print(
            f"reported cost: ${run_summary['total_reported_cost_usd']:.6f}{partial}"
        )
    else:
        print("reported cost: n/a")

    if run_summary["estimated_kwh"] is not None:
        print(
            f"estimated energy: {run_summary['estimated_kwh']:.4f} kWh "
            f"@ {a.power_watts:g} W assumed average"
        )
    if run_summary["estimated_electricity_cost"] is not None:
        cur = (a.electricity_currency + " ") if a.electricity_currency else ""
        print(
            "estimated electricity cost: "
            f"{cur}{run_summary['estimated_electricity_cost']:.4f}"
        )
    print("=" * 76)

    print("\\nDone:", run)
    print("Zip/send the whole run directory for comparison.")


if __name__ == "__main__":
    main()

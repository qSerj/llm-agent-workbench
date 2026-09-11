#!/usr/bin/env python3
"""Run a budget-capped matrix of OpenRouter image-to-video jobs."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.chain import run_directory
from workbench.envelope import file_artifact, validate_envelope
from workbench.experiment import read_yaml
from workbench.video import (
    VideoRequest,
    actual_cost,
    download_video,
    estimate_cost,
    model_by_id,
    redacted_payload,
    request_payload,
    submit_video,
    validate_request,
    video_models,
    wait_for_video,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def api_key() -> str:
    configured = os.environ.get("OPENROUTER_API_KEY")
    if configured:
        return configured
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        configured = auth["openrouter"]["key"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            "нет OPENROUTER_API_KEY и не найден ключ OpenRouter в хранилище OpenCode"
        ) from error
    if not isinstance(configured, str) or not configured:
        raise RuntimeError("пустой ключ OpenRouter")
    return configured


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_envelope(
    experiment_id: str,
    job_id: str,
    case_id: str,
    spec: VideoRequest,
    directory: Path,
    status: dict[str, Any],
    estimated_cost: float,
    wall_seconds: float,
    started_at: str,
) -> dict[str, Any]:
    prompt = directory / "prompt.txt"
    input_image = directory / f"input{spec.first_frame.suffix.lower()}"
    last_input = (
        directory / f"last-input{spec.last_frame.suffix.lower()}"
        if spec.last_frame is not None
        else None
    )
    request_log = directory / "request.json"
    status_log = directory / "status.json"
    video = directory / "output.mp4"
    cost = actual_cost(status)
    input_media_type = mimetypes.guess_type(input_image.name)[0] or "application/octet-stream"
    artifacts = [
        file_artifact("input-image", "INPUT", input_image, directory, input_media_type),
        file_artifact("prompt", "INPUT", prompt, directory, "text/plain"),
        file_artifact("request", "LOG", request_log, directory, "application/json"),
        file_artifact("response", "LOG", status_log, directory, "application/json"),
        file_artifact("video", "OUTPUT", video, directory, "video/mp4"),
    ]
    input_artifact_ids = ["input-image", "prompt"]
    if last_input is not None:
        last_media_type = mimetypes.guess_type(last_input.name)[0] or "application/octet-stream"
        artifacts.insert(
            1,
            file_artifact("last-input-image", "INPUT", last_input, directory, last_media_type),
        )
        input_artifact_ids.insert(1, "last-input-image")
    execution_id = f"{experiment_id}--{job_id}"
    return {
        "schema_version": "1.0",
        "execution_id": execution_id,
        "task": {"id": "animate-photo", "version": "1"},
        "case": {"id": case_id, "version": "1"},
        "candidate": {
            "id": spec.model,
            "version": "1",
            "parameters": {
                "duration": spec.duration,
                "size": spec.size,
                "generate_audio": spec.generate_audio,
            },
        },
        "repetition": 1,
        "lifecycle": {
            "status": "SUCCEEDED",
            "started_at": started_at,
            "finished_at": utc_now(),
            "timestamp_basis": "UTC system clock",
        },
        "executor": {
            "implementation": "workbench-openrouter-video",
            "version": "1",
            "exit_code": 0,
        },
        "artifacts": artifacts,
        "observations": [
            {
                "name": "wall_time",
                "value": round(wall_seconds, 6),
                "unit": "s",
                "method": "runner monotonic clock around submit, poll, and download",
            },
            {
                "name": "api_cost",
                "value": cost,
                "unit": "USD",
                "method": "OpenRouter completed-job usage; null when provider omitted it",
            },
            {
                "name": "estimated_api_cost",
                "value": round(estimated_cost, 12),
                "unit": "USD",
                "method": "live OpenRouter video model pricing before submission",
            },
        ],
        "stages": [
            {
                "id": "1-animation",
                "role": "SOLVER",
                "execution_id": f"{execution_id}::1-animation",
                "depends_on": [],
                "input_artifact_ids": input_artifact_ids,
                "output_artifact_ids": ["video"],
            }
        ],
        "evaluations": [],
        "correlations": [
            {
                "system": "openrouter",
                "kind": "generation_id",
                "value": str(status.get("generation_id") or status.get("id")),
            }
        ],
    }


def parse_jobs(document: dict[str, Any], root: Path) -> list[tuple[str, str, VideoRequest]]:
    jobs = []
    for raw in document.get("jobs") or []:
        job_id = str(raw["id"])
        case_id = str(raw.get("case") or job_id)
        first_frame = (root / str(raw["first_frame"])).resolve()
        last_frame = raw.get("last_frame")
        jobs.append(
            (
                job_id,
                case_id,
                VideoRequest(
                    model=str(raw["model"]),
                    prompt=str(raw["prompt"]),
                    duration=int(raw["duration"]),
                    size=str(raw["size"]),
                    first_frame=first_frame,
                    last_frame=(root / str(last_frame)).resolve() if last_frame else None,
                    generate_audio=bool(raw.get("generate_audio", False)),
                    seed=int(raw["seed"]) if raw.get("seed") is not None else None,
                ),
            )
        )
    if not jobs:
        raise ValueError("план не содержит jobs")
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path, default=Path("executions"))
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument(
        "--price-buffer",
        type=float,
        default=1.5,
        help="множитель резерва над ценой каталога; по умолчанию 1.5",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=1800)
    arguments = parser.parse_args()

    plan_path = arguments.plan.resolve()
    document = read_yaml(plan_path)
    if not isinstance(document, dict):
        raise ValueError("план должен быть отображением")
    experiment_id = str(document["id"])
    budget = arguments.budget_usd
    if budget is None:
        budget = float(document.get("budget_usd", 0))
    if budget <= 0:
        raise ValueError("нужен положительный --budget-usd или budget_usd")
    if arguments.price_buffer < 1:
        raise ValueError("--price-buffer должен быть не меньше 1")

    catalog = video_models()
    jobs = parse_jobs(document, ROOT)
    prepared = []
    for job_id, case_id, spec in jobs:
        model = model_by_id(catalog, spec.model)
        validate_request(spec, model)
        estimate = estimate_cost(model, spec.duration, spec.size, spec.generate_audio)
        prepared.append((job_id, case_id, spec, estimate))

    total_estimate = sum(item[3] for item in prepared)
    total_reserved = total_estimate * arguments.price_buffer
    print(f"Эксперимент: {experiment_id}")
    for job_id, _, spec, estimate in prepared:
        print(f"  {job_id}: {spec.model}, {spec.duration}s {spec.size}, ~${estimate:.6f}")
    print(
        f"План: ~${total_estimate:.6f}; резерв с множителем "
        f"{arguments.price_buffer:g}: ${total_reserved:.6f}; лимит: ${budget:.2f}"
    )
    if total_reserved > budget:
        raise RuntimeError("ценовой резерв плана превышает лимит; запросы не отправлены")
    if arguments.dry_run:
        return

    secret = api_key()
    today = datetime.now(UTC).date().isoformat()
    run_root = run_directory(arguments.output, experiment_id, today)
    spent_or_reserved = 0.0
    for job_id, case_id, spec, estimate in prepared:
        reserve = estimate * arguments.price_buffer
        if spent_or_reserved + reserve > budget:
            print(f"Лимит не допускает {job_id}; останавливаюсь")
            break
        directory = run_root / job_id
        directory.mkdir(parents=True)
        input_target = directory / f"input{spec.first_frame.suffix.lower()}"
        shutil.copy2(spec.first_frame, input_target)
        if spec.last_frame is not None:
            shutil.copy2(
                spec.last_frame,
                directory / f"last-input{spec.last_frame.suffix.lower()}",
            )
        (directory / "prompt.txt").write_text(spec.prompt + "\n", encoding="utf-8")
        write_json(directory / "request.json", redacted_payload(request_payload(spec)))

        print(f"\n{job_id}: отправляю, резерв ~${estimate:.6f}", flush=True)
        started_at = utc_now()
        started = time.monotonic()
        submitted = submit_video(spec, secret)
        write_json(directory / "submit.json", submitted)
        status = wait_for_video(
            submitted,
            secret,
            poll_seconds=arguments.poll_seconds,
            timeout_seconds=arguments.timeout,
        )
        write_json(directory / "status.json", status)
        if str(status.get("status", "")).lower() != "completed":
            raise RuntimeError(f"{job_id}: OpenRouter завершил задачу как {status.get('status')}")
        download_video(status, secret, directory / "output.mp4")
        elapsed = time.monotonic() - started
        charged = actual_cost(status)
        spent_or_reserved += charged if charged is not None else estimate
        envelope = build_envelope(
            experiment_id,
            job_id,
            case_id,
            spec,
            directory,
            status,
            estimate,
            elapsed,
            started_at,
        )
        validate_envelope(envelope)
        write_json(directory / "execution-envelope.json", envelope)
        print(
            f"  готово: {directory / 'output.mp4'}; "
            f"цена {'не сообщена' if charged is None else f'${charged:.6f}'}",
            flush=True,
        )

    print(f"\nУчтено по usage или оценке: ${spent_or_reserved:.6f}")


if __name__ == "__main__":
    main()

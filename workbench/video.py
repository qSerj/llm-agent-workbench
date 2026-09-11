"""Run bounded OpenRouter video jobs and record domain-neutral measurements."""

from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OPENROUTER_ROOT = "https://openrouter.ai"
VIDEO_MODELS_PATH = "/api/v1/videos/models"
VIDEO_CREATE_PATH = "/api/v1/videos"
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "expired"}


@dataclass(frozen=True)
class VideoRequest:
    model: str
    prompt: str
    duration: int
    size: str
    first_frame: Path
    last_frame: Path | None = None
    generate_audio: bool = False
    seed: int | None = None


def api_json(
    path_or_url: str,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    url = urllib.parse.urljoin(OPENROUTER_ROOT, path_or_url)
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {error.code}: {detail}") from error


def video_models() -> list[dict[str, Any]]:
    document = api_json(VIDEO_MODELS_PATH)
    models = document.get("data")
    if not isinstance(models, list):
        raise ValueError("OpenRouter video model catalog has no data array")
    return models


def model_by_id(models: list[dict[str, Any]], model_id: str) -> dict[str, Any]:
    for model in models:
        if model.get("id") == model_id:
            return model
    raise ValueError(f"unknown OpenRouter video model: {model_id}")


def parse_size(size: str) -> tuple[int, int]:
    try:
        width, height = (int(item) for item in size.lower().split("x", maxsplit=1))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid video size: {size}") from error
    if width < 1 or height < 1:
        raise ValueError(f"invalid video size: {size}")
    return width, height


def resolution_for(size: str) -> str:
    width, height = parse_size(size)
    short = min(width, height)
    if short <= 480:
        return "480p"
    if short <= 720:
        return "720p"
    return "1080p"


def estimate_cost(
    model: dict[str, Any], duration: int, size: str, generate_audio: bool
) -> float:
    """Estimate one request from the live model catalog, refusing ambiguity."""
    pricing = model.get("pricing_skus") or {}
    resolution = resolution_for(size)

    token_key = "video_tokens" if generate_audio else "video_tokens_without_audio"
    if token_key in pricing:
        width, height = parse_size(size)
        video_tokens = width * height * duration * 24 / 1024
        return video_tokens * float(pricing[token_key])

    candidates = []
    if generate_audio:
        candidates.extend(
            [f"duration_seconds_with_audio_{resolution}", "duration_seconds_with_audio"]
        )
    else:
        candidates.extend(
            [
                f"duration_seconds_without_audio_{resolution}",
                "duration_seconds_without_audio",
            ]
        )
    candidates.extend([f"duration_seconds_{resolution}", "duration_seconds"])
    for key in candidates:
        if key in pricing:
            return duration * float(pricing[key])

    cent_candidates = [
        f"cents_per_video_output_second_{resolution}",
        "cents_per_second_output",
    ]
    for key in cent_candidates:
        if key in pricing:
            cost = duration * float(pricing[key]) / 100
            if "cents_per_image_input" in pricing:
                cost += float(pricing["cents_per_image_input"]) / 100
            return cost

    raise ValueError(f"cannot estimate price for {model.get('id')} at {size}")


def validate_request(spec: VideoRequest, model: dict[str, Any]) -> None:
    if spec.duration not in (model.get("supported_durations") or []):
        raise ValueError(f"{spec.model} does not support duration {spec.duration}")
    if spec.size not in (model.get("supported_sizes") or []):
        raise ValueError(f"{spec.model} does not support size {spec.size}")
    frames = set(model.get("supported_frame_images") or [])
    if "first_frame" not in frames:
        raise ValueError(f"{spec.model} does not support a first frame")
    if spec.last_frame is not None and "last_frame" not in frames:
        raise ValueError(f"{spec.model} does not support a last frame")


def image_data_url(path: Path) -> str:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def request_payload(spec: VideoRequest) -> dict[str, Any]:
    frames = [
        {
            "type": "image_url",
            "image_url": {"url": image_data_url(spec.first_frame)},
            "frame_type": "first_frame",
        }
    ]
    if spec.last_frame is not None:
        frames.append(
            {
                "type": "image_url",
                "image_url": {"url": image_data_url(spec.last_frame)},
                "frame_type": "last_frame",
            }
        )
    payload: dict[str, Any] = {
        "model": spec.model,
        "prompt": spec.prompt,
        "duration": spec.duration,
        "size": spec.size,
        "generate_audio": spec.generate_audio,
        "frame_images": frames,
    }
    if spec.seed is not None:
        payload["seed"] = spec.seed
    return payload


def redacted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(payload))
    for frame in result.get("frame_images", []):
        url = frame.get("image_url", {}).get("url", "")
        if url.startswith("data:"):
            header, _, encoded = url.partition(",")
            frame["image_url"]["url"] = f"{header},<base64:{len(encoded)} chars>"
    return result


def submit_video(spec: VideoRequest, api_key: str) -> dict[str, Any]:
    return api_json(VIDEO_CREATE_PATH, api_key=api_key, payload=request_payload(spec), timeout=120)


def wait_for_video(
    job: dict[str, Any], api_key: str, poll_seconds: int = 15, timeout_seconds: int = 1800
) -> dict[str, Any]:
    started = time.monotonic()
    current = job
    while str(current.get("status", "")).lower() not in TERMINAL_STATUSES:
        if time.monotonic() - started >= timeout_seconds:
            raise TimeoutError(f"video job {job.get('id')} did not finish")
        polling_url = current.get("polling_url") or job.get("polling_url")
        if not polling_url:
            raise ValueError("OpenRouter video job has no polling_url")
        time.sleep(poll_seconds)
        current = api_json(str(polling_url), api_key=api_key, timeout=60)
        print(f"  {job.get('id')}: {current.get('status', 'unknown')}", flush=True)
    return current


def download_video(job: dict[str, Any], api_key: str, target: Path) -> None:
    urls = job.get("unsigned_urls") or []
    url = urls[0] if urls else f"{OPENROUTER_ROOT}/api/v1/videos/{job['id']}/content?index=0"
    headers = {"Authorization": f"Bearer {api_key}"} if url.startswith(OPENROUTER_ROOT) else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def actual_cost(job: dict[str, Any]) -> float | None:
    usage = job.get("usage")
    if not isinstance(usage, dict):
        return None
    for key in ("cost", "total_cost", "cost_usd"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None

#!/usr/bin/env python3
"""Reproduce the binary-artifact envelope experiment with ffmpeg/ffprobe."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workbench.envelope import file_artifact, validate_envelope


def run(command: list[str], log: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if log is not None:
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def probe(path: Path) -> dict:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,duration:format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout)


def build_candidate(bundle: Path, input_path: Path, candidate_id: str, correct: bool) -> Path:
    directory = bundle / candidate_id
    directory.mkdir()
    output = directory / "output.flac"
    log = directory / "ffmpeg.log"
    command = ["ffmpeg", "-y", "-i", str(input_path)]
    if correct:
        command += ["-ac", "1", "-ar", "16000"]
    else:
        command += ["-t", "1"]
    command.append(str(output))

    started = datetime.now(timezone.utc)
    before = time.monotonic()
    result = run(command, log)
    wall_seconds = time.monotonic() - before
    finished = datetime.now(timezone.utc)

    probe_result = probe(output)
    probe_path = directory / "ffprobe.json"
    probe_path.write_text(json.dumps(probe_result, indent=2) + "\n", encoding="utf-8")
    stream = probe_result["streams"][0]
    duration = float(probe_result["format"]["duration"])
    outcomes = {
        "codec_flac": stream["codec_name"] == "flac",
        "sample_rate_16000": int(stream["sample_rate"]) == 16000,
        "channels_mono": int(stream["channels"]) == 1,
        "duration_two_seconds": abs(duration - 2.0) <= 0.02,
    }
    checks = [
        {"id": name, "outcome": "PASS" if ok else "FAIL"}
        for name, ok in outcomes.items()
    ]
    score = sum(outcomes.values())
    envelope = {
        "schema_version": "1.0",
        "execution_id": f"audio-conversion:{bundle.name}:{candidate_id}",
        "task": {"id": "audio-convert-mono-16khz-flac", "version": "1"},
        "case": {"id": "stereo-48khz-two-second-sine", "version": "generated-v1"},
        "candidate": {
            "id": candidate_id,
            "version": "1",
            "parameters": {"command": command},
        },
        "repetition": 1,
        "lifecycle": {
            "status": "SUCCEEDED",
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "timestamp_basis": "utc-system-clock",
        },
        "executor": {
            "implementation": "ffmpeg",
            "version": run(["ffmpeg", "-version"]).stdout.splitlines()[0],
            "exit_code": result.returncode,
        },
        "artifacts": [
            file_artifact("source-wav", "INPUT", input_path, bundle, "audio/wav"),
            file_artifact("converted-flac", "OUTPUT", output, bundle, "audio/flac"),
            file_artifact("ffmpeg-log", "LOG", log, bundle, "text/plain"),
            file_artifact("ffprobe-evidence", "EVIDENCE", probe_path, bundle, "application/json"),
        ],
        "observations": [
            {"name": "wall_time", "value": wall_seconds, "unit": "s", "method": "monotonic-clock"},
            {"name": "output_bytes", "value": output.stat().st_size, "unit": "By", "method": "filesystem-stat"},
        ],
        "evaluations": [
            {
                "id": "audio-properties",
                "subject": {"kind": "ARTIFACT", "id": "converted-flac"},
                "evaluator": {"source": "CODE", "identity": "ffprobe-checks"},
                "policy": {"id": "mono-16khz-flac-two-seconds", "version": "1"},
                "result": {
                    "verdict": "PASS" if score == len(checks) else "FAIL",
                    "checks": checks,
                },
                "rationale": f"Passed {score}/{len(checks)} deterministic media checks.",
                "evidence_artifact_ids": ["source-wav", "converted-flac", "ffprobe-evidence"],
            }
        ],
        "correlations": [],
    }
    validate_envelope(envelope)
    envelope_path = directory / "execution-envelope.json"
    envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    return envelope_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise SystemExit(f"missing required executable: {executable}")

    bundle = args.output.resolve()
    bundle.mkdir(parents=True, exist_ok=False)
    input_path = bundle / "source.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=sin(2*PI*440*t)|sin(2*PI*660*t):s=48000:d=2",
            "-ac",
            "2",
            str(input_path),
        ]
    )
    for candidate_id, correct in (("ffmpeg-correct", True), ("ffmpeg-truncated", False)):
        path = build_candidate(bundle, input_path, candidate_id, correct)
        print(path)


if __name__ == "__main__":
    main()

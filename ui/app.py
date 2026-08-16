"""Local shell: list runs, inspect a chain, compare candidates, launch a run."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.charts import Row, Segment, legend, stacked_bars
from ui.store import ROLE_SLOTS, Run, Store

EXECUTIONS = Path(os.environ.get("WORKBENCH_EXECUTIONS", ROOT / "executions"))
EXPERIMENTS = ROOT / "experiments"
LOGS = EXECUTIONS / ".launch-logs"

app = FastAPI(title="Workbench")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
store = Store(EXECUTIONS)


@dataclass
class Job:
    id: str
    experiment: str
    candidates: list[str]
    started_at: str
    log_path: Path
    process: subprocess.Popen = field(repr=False)

    @property
    def running(self) -> bool:
        return self.process.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self.process.poll()

    def tail(self, limit: int = 4000) -> str:
        if not self.log_path.is_file():
            return ""
        text = self.log_path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:]


JOBS: dict[str, Job] = {}


def format_seconds(value: float) -> str:
    return f"{value:.0f}" if value >= 10 else f"{value:.1f}"


def format_usd(value: float) -> str:
    return f"{value:.4f}" if value >= 0.01 else f"{value:.5f}"


def tick_seconds(value: float) -> str:
    return f"{value:.0f}"


def tick_usd(value: float) -> str:
    # Four decimals, because the step is often 0.0025: rounding to three makes
    # an even scale read as an uneven one (0.003, 0.005, 0.007, 0.010).
    return f"{value:.4f}"


def roles_in(runs: list[Run]) -> list[tuple[str, int]]:
    """Legend entries in fixed slot order, only for roles actually present."""
    present = {stage.role for run in runs for stage in run.stages}
    ordered = sorted(present, key=lambda role: ROLE_SLOTS.get(role, 4))
    return [(role, ROLE_SLOTS.get(role, 4)) for role in ordered]


def chart_rows(runs: list[Run], measurement: str) -> list[Row]:
    rows = []
    for run in runs:
        segments = [
            Segment(
                label=stage.role.title(),
                slot=stage.slot,
                value=float(getattr(stage, measurement) or 0.0),
            )
            for stage in run.stages
        ]
        total = run.wall_time if measurement == "wall_time" else run.api_cost
        rows.append(
            Row(label=f"{run.candidate_id}·r{run.repetition}", segments=segments, total=total)
        )
    return rows


def comparison_charts(runs: list[Run]) -> dict[str, str]:
    """Two measures of different scale get two charts, never two y-axes."""
    return {
        "time": stacked_bars(
            chart_rows(runs, "wall_time"), "с", format_seconds, tick_seconds
        ),
        "cost": stacked_bars(
            chart_rows(runs, "api_cost"), "$", format_usd, tick_usd
        ),
        "legend": legend(roles_in(runs)),
    }


def available_experiments() -> list[str]:
    if not EXPERIMENTS.is_dir():
        return []
    return sorted(path.name for path in EXPERIMENTS.glob("*.yaml"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    experiments = store.experiments()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "experiments": experiments,
            "available": available_experiments(),
            "jobs": sorted(JOBS.values(), key=lambda job: job.started_at, reverse=True),
            "executions_root": EXECUTIONS,
        },
    )


@app.get("/run/{execution_id}", response_class=HTMLResponse)
def run_detail(request: Request, execution_id: str) -> Any:
    run = store.run(execution_id)
    if run is None:
        raise HTTPException(status_code=404, detail="карточка не найдена")
    charts = comparison_charts([run])
    return templates.TemplateResponse(
        request=request,
        name="run.html",
        context={"run": run, "charts": charts},
    )


@app.get("/compare", response_class=HTMLResponse)
def compare(request: Request, id: list[str] | None = None) -> Any:
    runs = store.select(id or [])
    if not runs:
        runs = store.runs()
    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "runs": runs,
            "charts": comparison_charts(runs),
            "selected": {run.execution_id for run in runs},
            "all_runs": store.runs(),
        },
    )


@app.get("/artifact/{execution_id}/{relative_path:path}", response_class=PlainTextResponse)
def artifact(execution_id: str, relative_path: str) -> Any:
    run = store.run(execution_id)
    if run is None:
        raise HTTPException(status_code=404, detail="карточка не найдена")
    directory = run.directory.resolve()
    target = (directory / relative_path).resolve()
    if not target.is_relative_to(directory) or not target.is_file():
        raise HTTPException(status_code=404, detail="артефакт не найден")
    if target.stat().st_size > 2_000_000:
        raise HTTPException(status_code=413, detail="артефакт слишком велик")
    return target.read_text(encoding="utf-8", errors="replace")


@app.post("/launch")
async def launch(request: Request) -> Any:
    # The form is parsed here rather than with fastapi.Form so the shell needs
    # no python-multipart: an ordinary HTML form posts urlencoded data.
    fields = parse_qs((await request.body()).decode("utf-8"))
    experiment = (fields.get("experiment") or [""])[0]
    candidates = (fields.get("candidates") or [""])[0]

    path = (EXPERIMENTS / experiment).resolve()
    if not path.is_relative_to(EXPERIMENTS.resolve()) or not path.is_file():
        raise HTTPException(status_code=400, detail="неизвестный эксперимент")

    selected = [item.strip() for item in candidates.split(",") if item.strip()]
    command = [sys.executable, str(ROOT / "tools" / "run_chain.py"), str(path)]
    command += ["--output", str(EXECUTIONS)]
    for name in selected:
        command += ["--candidate", name]

    LOGS.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    log_path = LOGS / f"{job_id}.log"
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, text=True
    )
    JOBS[job_id] = Job(
        id=job_id,
        experiment=experiment,
        candidates=selected,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        log_path=log_path,
        process=process,
    )
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str) -> Any:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="запуск не найден")
    return templates.TemplateResponse(
        request=request,
        name="job.html",
        context={"job": job},
    )

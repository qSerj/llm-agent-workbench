"""Local shell: list runs, inspect a chain, compare candidates, launch a run."""

from __future__ import annotations

import json
import os
import re
import shutil
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
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.charts import Row, Segment, legend, stacked_bars
from ui.store import ROLE_SLOTS, Run, Store
from workbench.draft import draft_experiment
from workbench.evalform import EVALUATOR_FORMS, form_rows, hidden_rows
from workbench.evaluators import options_for
from workbench.experiment import (
    STAGE_ROLES,
    blank_document,
    dump_experiment,
    experiment_document,
    leading_comment,
    parse_experiment,
    read_yaml,
    reference_text,
)
from workbench.storage import is_hidden, move_to_trash
from workbench.textdiff import diff_lines, differing_prompts, stage_rows

DESCRIPTION_NAME = "experiment.yaml"

EXECUTIONS = Path(os.environ.get("WORKBENCH_EXECUTIONS", ROOT / "executions"))
EXPERIMENTS = ROOT / "experiments"
LOGS = EXECUTIONS / ".launch-logs"

app = FastAPI(title="Workbench")
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)
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
        rows.append(Row(label=run.label, segments=segments, total=total))
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
    """Directory names under experiments/ that carry a description."""
    if not EXPERIMENTS.is_dir():
        return []
    return sorted(
        path.parent.name
        for path in EXPERIMENTS.glob(f"*/{DESCRIPTION_NAME}")
        if not is_hidden(path, EXPERIMENTS)
    )


def description_path(name: str) -> Path:
    """Resolve an experiment name to its description, refusing anything outside."""
    path = (EXPERIMENTS / name / DESCRIPTION_NAME).resolve()
    if not path.is_relative_to(EXPERIMENTS.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="эксперимент не найден")
    return path


def normalised(document: Any, name: str) -> dict[str, Any]:
    """Fill the fields the form always shows, so a short file still renders."""
    if not isinstance(document, dict):
        raise HTTPException(status_code=400, detail="описание должно быть отображением")
    draft = dict(document)
    draft.setdefault("id", name)
    draft.setdefault("question", "")
    draft.setdefault("workspace", "")
    draft.setdefault("task", draft["id"])
    draft.setdefault("case", Path(str(draft["workspace"])).name)
    draft.setdefault("repetitions", 1)
    # The form works with mappings; the shorthand `citations: path.md` is a
    # writing style that dump_experiment restores on the way out.
    raw_evaluate = draft.get("evaluate") or {}
    draft["evaluate"] = (
        {str(name): options_for(value) for name, value in raw_evaluate.items()}
        if isinstance(raw_evaluate, dict)
        else {}
    )
    candidates = []
    for candidate in draft.get("candidates") or []:
        stages = [dict(stage) for stage in (candidate.get("stages") or [])]
        candidates.append({"id": candidate.get("id", ""), "stages": stages})
    draft["candidates"] = candidates
    draft["task"] = reference_text(draft["task"])
    draft["case"] = reference_text(draft["case"])
    return draft


def blank_stage() -> dict[str, Any]:
    return {"role": "OTHER", "model": "", "prompt": "", "allow_edit": []}


def apply_structure(draft: dict[str, Any], action: str) -> None:
    """Add or drop a candidate or a stage. The draft lives in the form itself."""
    verb, _, target = action.partition(":")
    parts = [int(item) for item in target.split(":") if item.isdigit()]
    candidates = draft["candidates"]
    if verb == "add-candidate":
        candidates.append({"id": "", "stages": [blank_stage()]})
    elif verb == "remove-candidate" and parts:
        if 0 <= parts[0] < len(candidates):
            del candidates[parts[0]]
    elif verb == "add-stage" and parts:
        if 0 <= parts[0] < len(candidates):
            candidates[parts[0]]["stages"].append(blank_stage())
    elif verb == "remove-stage" and len(parts) == 2:
        row, column = parts
        if 0 <= row < len(candidates):
            stages = candidates[row]["stages"]
            if 0 <= column < len(stages):
                del stages[column]


MODEL_CACHE: list[str] = []


def known_models() -> list[str]:
    """Models OpenCode can already reach, so nothing has to be typed from memory.

    Asked once per process: the list costs a couple of seconds and does not
    change under us. A failure here is not fatal — the field stays free text.
    """
    if MODEL_CACHE:
        return MODEL_CACHE
    try:
        finished = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"список моделей недоступен: {error}")
        return []
    for line in finished.stdout.splitlines():
        name = line.strip()
        provider, _, model = name.partition("/")
        # The description stores the model as the provider names it, without the
        # OpenCode provider prefix that this listing carries.
        if provider == "openrouter" and model:
            MODEL_CACHE.append(model)
    MODEL_CACHE.sort()
    return MODEL_CACHE


def workspace_files(workspace: Path, limit: int = 400) -> list[str]:
    """Paths a stage could be allowed to edit, relative to the workspace."""
    if not workspace.is_dir():
        return []
    found = []
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            found.append(str(path.relative_to(workspace)))
        if len(found) >= limit:
            break
    return found


def prompt_files(directory: Path) -> dict[str, str]:
    """Every prompt kept beside the description, ready to edit."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.md"))
    }


def external_prompts(draft: dict[str, Any], directory: Path) -> list[str]:
    """Prompts living outside the experiment directory: shown, never edited."""
    found = []
    for candidate in draft["candidates"]:
        for stage in candidate["stages"]:
            prompt = str(stage.get("prompt") or "")
            if not prompt:
                continue
            resolved = (ROOT / prompt).resolve()
            if not resolved.is_relative_to(directory) and prompt not in found:
                found.append(prompt)
    return found


def evaluation_blocks(evaluate: dict[str, Any]) -> list[dict[str, Any]]:
    """Every evaluation the registry knows, plus any the description carries.

    An unknown name is shown too, as its own settings and a warning, so that a
    description written by hand is never quietly emptied by a save.
    """
    blocks: list[dict[str, Any]] = []
    for name, form in EVALUATOR_FORMS.items():
        options = evaluate.get(name) or {}
        blocks.append(
            {
                "name": name,
                "form": form,
                "enabled": name in evaluate,
                "rows": form_rows(name, options),
                "hidden": hidden_rows(name, options),
                "known": True,
            }
        )
    for name, options in evaluate.items():
        if name in EVALUATOR_FORMS:
            continue
        blocks.append(
            {
                "name": name,
                "form": None,
                "enabled": True,
                "rows": [],
                "hidden": hidden_rows(name, options or {}),
                "known": False,
            }
        )
    return blocks


def editor_context(
    request: Request,
    name: str,
    draft: dict[str, Any],
    prompts: dict[str, str],
    error: str = "",
    saved: bool = False,
) -> Any:
    directory = (EXPERIMENTS / name).resolve()
    return templates.TemplateResponse(
        request=request,
        name="experiment.html",
        context={
            "name": name,
            "draft": draft,
            "prompts": prompts,
            "external": external_prompts(draft, directory),
            "roles": sorted(STAGE_ROLES),
            "models": known_models(),
            "prompt_paths": sorted(
                str(item.relative_to(ROOT)) for item in directory.glob("*.md")
            ),
            "workspace_paths": workspace_files(
                (ROOT / str(draft.get("workspace") or "")).resolve()
            ),
            "columns": max(
                (len(item["stages"]) for item in draft["candidates"]), default=0
            ),
            "evaluations": evaluation_blocks(draft.get("evaluate") or {}),
            "error": error,
            "saved": saved,
            "directory": directory,
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    # Grouped by sitting, newest first: runs from different days in one table
    # invite a comparison that is not sound.
    sessions = [
        {"experiment": experiment, "session": session, "runs": group}
        for (experiment, session), group in sorted(
            store.sessions().items(), key=lambda item: item[0], reverse=True
        )
    ]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "sessions": sessions,
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
    # Comparing everything compares runs from different days in one table, and
    # a chain run a day later is a different measurement. Without a choice, show
    # the most recent sitting.
    runs = store.select(id or [])
    if not runs:
        runs = store.latest_session()
    sessions = [
        {
            "experiment": experiment,
            "session": session,
            "ids": [run.execution_id for run in group],
            "moment": min(run.moment for run in group),
            "count": len(group),
        }
        for (experiment, session), group in sorted(store.sessions().items())
    ]
    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "runs": runs,
            "charts": comparison_charts(runs),
            "selected": {run.execution_id for run in runs},
            "all_runs": store.runs(),
            "sessions": sessions,
            "showing_all": bool(id),
        },
    )


@app.get("/run-diff", response_class=HTMLResponse)
def run_diff(request: Request, a: str = "", b: str = "") -> Any:
    """Diff the documents two runs produced, which is the result itself."""
    left, right = store.run(a), store.run(b)
    if left is None or right is None:
        raise HTTPException(status_code=404, detail="прогон не найден")

    def document(run: Run) -> tuple[str, str]:
        for artifact in run.artifacts:
            if artifact["id"] == "final-document" and "path" in artifact["location"]:
                path = run.directory / artifact["location"]["path"]
                if path.is_file():
                    return artifact["location"]["path"], path.read_text(
                        encoding="utf-8", errors="replace"
                    )
        return "", ""

    left_path, left_text = document(left)
    right_path, right_text = document(right)
    return templates.TemplateResponse(
        request=request,
        name="run-diff.html",
        context={
            "left": left,
            "right": right,
            "left_path": left_path,
            "right_path": right_path,
            "rows": diff_lines(left_text, right_text, left.label, right.label),
            "missing": not left_text and not right_text,
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


def experiment_summary(name: str) -> dict[str, Any]:
    """Enough of a description to tell experiments apart in a list."""
    path = EXPERIMENTS / name / DESCRIPTION_NAME
    summary: dict[str, Any] = {"name": name, "question": "", "candidates": [], "error": ""}
    try:
        document = read_yaml(path)
        summary["question"] = str(document.get("question", ""))
        summary["workspace"] = str(document.get("workspace", ""))
        summary["candidates"] = [
            {
                "id": str(item.get("id", "")),
                "chain": " → ".join(
                    str(stage.get("role", "?")) for stage in (item.get("stages") or [])
                ),
            }
            for item in (document.get("candidates") or [])
        ]
    except (OSError, ValueError, KeyError, AttributeError) as error:
        summary["error"] = str(error)
    return summary


@app.get("/experiments", response_class=HTMLResponse)
def experiments_index(request: Request) -> Any:
    return templates.TemplateResponse(
        request=request,
        name="experiments.html",
        context={
            "experiments": [experiment_summary(name) for name in available_experiments()],
            "runs_by_experiment": {
                experiment: len(runs) for experiment, runs in store.experiments().items()
            },
        },
    )


@app.get("/experiment/new", response_class=HTMLResponse)
def experiment_new(request: Request) -> Any:
    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context={"models": known_models(), "form": {}, "draft": None, "error": ""},
    )


def draft_form(fields: dict[str, list[str]]) -> dict[str, str]:
    return {
        key: (fields.get(key) or [""])[0].strip()
        for key in ("name", "description", "success", "workspace", "model", "provider")
    }


@app.post("/experiment/new", response_class=HTMLResponse)
async def experiment_create(request: Request) -> Any:
    fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    action = (fields.get("action") or [""])[0]
    form = draft_form(fields)

    def again(error: str = "", draft: dict[str, Any] | None = None) -> Any:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context={
                "models": known_models(),
                "form": form,
                "draft": draft,
                "error": error,
            },
        )

    name = form["name"] or ""
    if action in {"draft", "blank"}:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            return again("имя каталога: строчные латинские буквы, цифры и дефис")
        if (EXPERIMENTS / name).exists():
            return again(f"эксперимент {name} уже есть")

    if action == "blank":
        document = blank_document(name, form["description"], form["workspace"])
        return again(draft={"document": document, "prompts": {"task.md": ""}, "cost": None})

    if action == "draft":
        workspace = (ROOT / form["workspace"]).resolve()
        if not workspace.is_dir():
            return again(f"нет каталога: {workspace}")
        if not form["model"]:
            return again("выберите модель-составителя")
        try:
            result = draft_experiment(
                description=form["description"],
                success=form["success"],
                workspace=workspace,
                model=form["model"],
                provider=form["provider"] or "openrouter",
            )
        except (ValueError, OSError, json.JSONDecodeError) as error:
            return again(f"составитель не справился: {error}")
        document = dict(result["document"])
        document["id"] = name
        document["workspace"] = form["workspace"]
        for candidate in document.get("candidates") or []:
            for stage in candidate.get("stages") or []:
                stage["prompt"] = f"experiments/{name}/{Path(str(stage.get('prompt'))).name}"
        return again(
            draft={
                "document": document,
                "prompts": result["prompts"],
                "cost": result["api_cost_usd"],
                "model": result["model"],
                "seconds": result["wall_seconds"],
            }
        )

    if action == "create":
        return write_new_experiment(fields, name, again)

    raise HTTPException(status_code=400, detail="неизвестное действие")


def write_new_experiment(fields: dict[str, list[str]], name: str, again: Any) -> Any:
    """Create the directory only once the draft passes the runner's own checks."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or ""):
        return again("имя каталога: строчные латинские буквы, цифры и дефис")
    directory = (EXPERIMENTS / name).resolve()
    if not directory.is_relative_to(EXPERIMENTS.resolve()):
        raise HTTPException(status_code=400, detail="имя вне каталога experiments")
    if directory.exists():
        return again(f"эксперимент {name} уже есть")

    prompts = {
        key[len("prompt.") :]: value[0].replace("\r\n", "\n")
        for key, value in fields.items()
        if key.startswith("prompt.")
    }
    document = experiment_document(fields)

    directory.mkdir(parents=True)
    try:
        for filename, text in prompts.items():
            target = (directory / filename).resolve()
            if not target.is_relative_to(directory) or target.suffix != ".md":
                raise ValueError(f"промпт вне каталога эксперимента: {filename}")
            target.write_text(text, encoding="utf-8")
        experiment = parse_experiment(document, root=ROOT, where=str(directory))
        (directory / DESCRIPTION_NAME).write_text(
            dump_experiment(experiment, root=ROOT), encoding="utf-8"
        )
    except (ValueError, KeyError, OSError) as error:
        shutil.rmtree(directory, ignore_errors=True)
        return again(
            str(error),
            draft={"document": document, "prompts": prompts, "cost": None},
        )
    return RedirectResponse(url=f"/experiment/{name}?saved=true", status_code=303)


@app.post("/experiment/{name}/delete")
def experiment_delete(name: str) -> Any:
    """Move an experiment to the trash. Its runs are left alone: they happened."""
    directory = (EXPERIMENTS / name).resolve()
    try:
        move_to_trash(directory, EXPERIMENTS.resolve())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return RedirectResponse(url="/experiments", status_code=303)


@app.post("/runs/delete")
async def runs_delete(request: Request) -> Any:
    """Move the selected runs to the trash, so a costly result is recoverable."""
    fields = parse_qs((await request.body()).decode("utf-8"))
    for execution_id in fields.get("id") or []:
        run = store.run(execution_id)
        if run is not None:
            move_to_trash(run.directory, EXECUTIONS.resolve())
    return RedirectResponse(url="/compare", status_code=303)


@app.get("/experiment/{name}/diff", response_class=HTMLResponse)
def experiment_diff(request: Request, name: str, a: str = "", b: str = "") -> Any:
    """Say what actually separates two candidates: their chain and their prompts."""
    path = description_path(name)
    document = normalised(read_yaml(path), name)
    by_id = {item["id"]: item for item in document["candidates"]}
    names = list(by_id)
    left_id = a if a in by_id else (names[0] if names else "")
    right_id = b if b in by_id else (names[1] if len(names) > 1 else left_id)

    def read(prompt: str) -> str:
        if not prompt:
            return ""
        target = (ROOT / prompt).resolve()
        return (
            target.read_text(encoding="utf-8", errors="replace")
            if target.is_file()
            else ""
        )

    left = by_id.get(left_id, {}).get("stages") or []
    right = by_id.get(right_id, {}).get("stages") or []
    return templates.TemplateResponse(
        request=request,
        name="experiment-diff.html",
        context={
            "name": name,
            "candidates": names,
            "left_id": left_id,
            "right_id": right_id,
            "rows": stage_rows(left, right),
            "prompts": differing_prompts(left, right, read),
        },
    )


@app.get("/experiment/{name}", response_class=HTMLResponse)
def experiment_editor(request: Request, name: str, saved: bool = False) -> Any:
    path = description_path(name)
    draft = normalised(read_yaml(path), name)
    return editor_context(
        request, name, draft, prompt_files(path.parent), saved=saved
    )


@app.post("/experiment/{name}", response_class=HTMLResponse)
async def experiment_save(request: Request, name: str) -> Any:
    path = description_path(name)
    directory = path.parent
    fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    action = (fields.get("action") or ["save"])[0]

    draft = normalised(experiment_document(fields), name)
    edited = {
        key[len("prompt.") :]: value[0].replace("\r\n", "\n")
        for key, value in fields.items()
        if key.startswith("prompt.")
    }
    new_name = (fields.get("new_prompt_name") or [""])[0].strip()
    if new_name:
        edited[new_name] = (
            (fields.get("new_prompt_text") or [""])[0].replace("\r\n", "\n")
        )

    if action != "save":
        apply_structure(draft, action)
        return editor_context(request, name, draft, edited or prompt_files(directory))

    # Prompts are written first so a stage may point at a file this very edit
    # creates. A draft that fails validation is rolled back to the byte, which is
    # what "nothing is written unless it is valid" has to mean here.
    restore: dict[Path, str | None] = {}
    try:
        for relative, text in edited.items():
            target = (directory / relative).resolve()
            if not target.is_relative_to(directory) or target.suffix != ".md":
                raise ValueError(f"промпт вне каталога эксперимента: {relative}")
            restore[target] = (
                target.read_text(encoding="utf-8") if target.is_file() else None
            )
            target.write_text(text, encoding="utf-8")

        experiment = parse_experiment(
            experiment_document(fields), root=ROOT, where=str(path)
        )
    except (ValueError, KeyError, OSError) as error:
        for target, previous in restore.items():
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(previous, encoding="utf-8")
        return editor_context(request, name, draft, edited, error=str(error))

    header = leading_comment(path.read_text(encoding="utf-8"))
    path.write_text(dump_experiment(experiment, root=ROOT, header=header), encoding="utf-8")
    return RedirectResponse(url=f"/experiment/{name}?saved=true", status_code=303)


@app.post("/launch")
async def launch(request: Request) -> Any:
    # The form is parsed here rather than with fastapi.Form so the shell needs
    # no python-multipart: an ordinary HTML form posts urlencoded data.
    fields = parse_qs((await request.body()).decode("utf-8"))
    experiment = (fields.get("experiment") or [""])[0]
    candidates = (fields.get("candidates") or [""])[0]

    path = description_path(experiment)
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

"""Pipeline run endpoints: trigger, status, SSE stream."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from pydantic import BaseModel

from api.app.database import SessionLocal, get_db
from api.app.models import Hackathon, PipelineRun
from api.app.schemas import RunCreate, RunResponse
from api.app.services import storage
from api.app.services.pipeline import execute_pipeline
from api.app.services.retry import retry_items

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _phases_blocking(phase: str) -> set[str]:
    """Phases of an active run that block starting a new run with `phase`.

    A "full" run touches every stage, so any other phase conflicts with it.
    Acquisition and Analysis are otherwise independent.
    """
    if phase == "full":
        return {"acquisition", "analysis", "full"}
    if phase == "acquisition":
        return {"acquisition", "full"}
    if phase == "analysis":
        return {"analysis", "full"}
    return set()


def _run_pipeline_in_thread(run_id: str, resume: bool) -> None:
    """Execute pipeline with its own DB session (runs in a background thread)."""
    db = SessionLocal()
    try:
        execute_pipeline(db, run_id, resume=resume)
    finally:
        db.close()


@router.post(
    "",
    response_model=RunResponse,
    status_code=201,
    summary="Trigger a pipeline run",
)
def create_run(
    hackathon_id: str,
    body: RunCreate | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")
    if not h.csv_filename:
        raise HTTPException(400, "Upload a CSV before running the pipeline")

    phase = body.phase if body else "full"
    if phase not in ("acquisition", "analysis", "full"):
        raise HTTPException(400, f"Invalid phase '{phase}'")

    # Acquisition and Analysis are independent enough to run concurrently.
    # A "full" run does both, so it conflicts with everything.
    blocking = _phases_blocking(phase)
    active = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.hackathon_id == hackathon_id,
            PipelineRun.status.in_(["pending", "running"]),
            PipelineRun.phase.in_(list(blocking)),
        )
        .first()
    )
    if active:
        raise HTTPException(
            409,
            f"A {active.phase} run is already {active.status} (id={active.id})",
        )

    run = PipelineRun(hackathon_id=hackathon_id, phase=phase)
    db.add(run)
    db.commit()
    db.refresh(run)

    resume = body.resume if body else True
    background_tasks.add_task(_run_pipeline_in_thread, run.id, resume)

    return run


@router.post("/{run_id}/resume", response_model=RunResponse, summary="Resume an interrupted or failed run")
def resume_run(
    run_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in ("interrupted", "failed"):
        raise HTTPException(400, f"Run is '{run.status}', can only resume interrupted or failed runs")

    blocking = _phases_blocking(run.phase or "full")
    active = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.hackathon_id == run.hackathon_id,
            PipelineRun.status.in_(["pending", "running"]),
            PipelineRun.phase.in_(list(blocking)),
        )
        .first()
    )
    if active:
        raise HTTPException(
            409, f"A {active.phase} run is already {active.status}",
        )

    run.status = "running"
    run.error = None
    run.cancel_requested = False
    db.commit()
    db.refresh(run)

    background_tasks.add_task(_run_pipeline_in_thread, run.id, True)
    return run


@router.post("/{run_id}/stop", response_model=RunResponse, summary="Request a graceful stop of a running pipeline")
def stop_run(run_id: str, db: Session = Depends(get_db)):
    """Set the cancel flag. The worker thread checks it on every per-team
    progress update and aborts within ~one team's processing time.
    Already-completed work is preserved; the run becomes 'interrupted' and
    can be resumed later.
    """
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in ("pending", "running"):
        raise HTTPException(400, f"Run is '{run.status}', not running")
    run.cancel_requested = True
    db.commit()
    db.refresh(run)
    return run


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/{run_id}/stream")
async def stream_run(run_id: str):
    """SSE endpoint that emits run status updates until the run finishes."""

    async def event_generator():
        prev_payload = None
        while True:
            db = SessionLocal()
            try:
                run = db.get(PipelineRun, run_id)
                if not run:
                    yield {"event": "error", "data": json.dumps({"error": "Run not found"})}
                    return

                payload = json.dumps({
                    "id": run.id,
                    "status": run.status,
                    "current_stage": run.current_stage,
                    "stage_progress": run.stage_progress or {},
                    "stage_detail": run.stage_detail or {},
                    "error": run.error,
                    "cancel_requested": bool(run.cancel_requested),
                })

                if payload != prev_payload:
                    yield {"event": "status", "data": payload}
                    prev_payload = payload

                if run.status in ("completed", "failed", "interrupted"):
                    return
            finally:
                db.close()

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


class RetryRequest(BaseModel):
    stage: str
    team_numbers: list[int]


@router.post("/{run_id}/retry", summary="Retry specific failed items within a stage")
def retry_run_items(
    run_id: str,
    body: RetryRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status in ("pending", "running"):
        raise HTTPException(400, "Cannot retry while pipeline is running")

    valid_stages = {"clone", "video_download", "code_review", "video_analysis"}
    if body.stage not in valid_stages:
        raise HTTPException(400, f"Retry not supported for stage '{body.stage}'. Supported: {valid_stages}")

    background_tasks.add_task(_retry_in_thread, run.id, body.stage, body.team_numbers)
    return {"status": "retrying", "stage": body.stage, "team_numbers": body.team_numbers}


def _retry_in_thread(run_id: str, stage: str, team_numbers: list[int]) -> None:
    db = SessionLocal()
    try:
        retry_items(db, run_id, stage, team_numbers)
    finally:
        db.close()


@router.get("/{run_id}/logs/{stage}", summary="Read the captured log for a single stage")
def get_stage_log(run_id: str, stage: str, db: Session = Depends(get_db)):
    from api.app.models import PIPELINE_STAGES
    if stage not in PIPELINE_STAGES:
        raise HTTPException(400, f"Unknown stage '{stage}'")

    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    log_path = storage.run_logs_dir(run.hackathon_id, run.id) / f"{stage}.log"
    if not log_path.exists():
        return {"stage": stage, "exists": False, "content": "", "size": 0}

    size = log_path.stat().st_size
    content = log_path.read_text(encoding="utf-8", errors="replace")
    # Strip carriage-return cursor overwrites left over from tqdm progress bars.
    # Each \r segment becomes its own line so the file reads top-to-bottom.
    content = content.replace("\r", "\n")
    return {"stage": stage, "exists": True, "content": content, "size": size}


@router.get("/{run_id}/videos.zip", summary="Download all downloaded videos as a zip")
def download_videos_zip(run_id: str, db: Session = Depends(get_db)):
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    videos_dir = storage.run_videos_dir(run.hackathon_id, run.id)
    if not videos_dir.exists():
        raise HTTPException(404, "No videos directory for this run")

    files = sorted(p for p in videos_dir.iterdir() if p.is_file())
    if not files:
        raise HTTPException(404, "No videos to download")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    try:
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:
            for path in files:
                zf.write(path, arcname=path.name)
    except Exception:
        os.unlink(tmp.name)
        raise

    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"videos-{run.id[:8]}.zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )


@router.get("", response_model=list[RunResponse])
def list_runs(hackathon_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.hackathon_id == hackathon_id)
        .order_by(PipelineRun.created_at.desc())
        .all()
    )
    return runs

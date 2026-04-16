"""Pipeline run endpoints: trigger, status, SSE stream."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from pydantic import BaseModel

from api.app.database import SessionLocal, get_db
from api.app.models import Hackathon, PipelineRun
from api.app.schemas import RunCreate, RunResponse
from api.app.services.pipeline import execute_pipeline
from api.app.services.retry import retry_items

router = APIRouter(prefix="/api/runs", tags=["runs"])


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

    active = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.hackathon_id == hackathon_id,
            PipelineRun.status.in_(["pending", "running"]),
        )
        .first()
    )
    if active:
        raise HTTPException(409, f"A run is already {active.status} (id={active.id})")

    run = PipelineRun(hackathon_id=hackathon_id)
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

    active = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.hackathon_id == run.hackathon_id,
            PipelineRun.status.in_(["pending", "running"]),
        )
        .first()
    )
    if active:
        raise HTTPException(409, f"Another run is already {active.status}")

    run.status = "running"
    run.error = None
    db.commit()
    db.refresh(run)

    background_tasks.add_task(_run_pipeline_in_thread, run.id, True)
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


@router.get("", response_model=list[RunResponse])
def list_runs(hackathon_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.hackathon_id == hackathon_id)
        .order_by(PipelineRun.created_at.desc())
        .all()
    )
    return runs

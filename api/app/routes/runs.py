"""Pipeline run endpoints: trigger, status, SSE stream."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from api.app.database import SessionLocal, get_db
from api.app.models import Hackathon, PipelineRun
from api.app.schemas import RunCreate, RunResponse
from api.app.services.pipeline import execute_pipeline

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
                    "error": run.error,
                })

                if payload != prev_payload:
                    yield {"event": "status", "data": payload}
                    prev_payload = payload

                if run.status in ("completed", "failed"):
                    return
            finally:
                db.close()

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("", response_model=list[RunResponse])
def list_runs(hackathon_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.hackathon_id == hackathon_id)
        .order_by(PipelineRun.created_at.desc())
        .all()
    )
    return runs

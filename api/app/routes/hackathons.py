"""CRUD endpoints for hackathons + CSV upload."""

from __future__ import annotations

import csv
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.app.database import get_db
from api.app.models import Hackathon, PipelineRun
from api.app.schemas import (
    HackathonCreate,
    HackathonListResponse,
    HackathonResponse,
    HackathonUpdate,
)
from api.app.services import storage

router = APIRouter(prefix="/api/hackathons", tags=["hackathons"])


@router.post("", response_model=HackathonResponse, status_code=201)
def create_hackathon(body: HackathonCreate, db: Session = Depends(get_db)):
    h = Hackathon(name=body.name, config=body.config)
    db.add(h)
    db.commit()
    db.refresh(h)
    storage.ensure_hackathon_dir(h.id)
    return h


@router.get("", response_model=list[HackathonListResponse])
def list_hackathons(db: Session = Depends(get_db)):
    hackathons = db.query(Hackathon).order_by(Hackathon.created_at.desc()).all()
    results = []
    for h in hackathons:
        latest_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.hackathon_id == h.id)
            .order_by(PipelineRun.created_at.desc())
            .first()
        )
        results.append(HackathonListResponse(
            id=h.id,
            name=h.name,
            csv_filename=h.csv_filename,
            created_at=h.created_at,
            latest_run_status=latest_run.status if latest_run else None,
        ))
    return results


@router.get("/{hackathon_id}", response_model=HackathonResponse)
def get_hackathon(hackathon_id: str, db: Session = Depends(get_db)):
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")
    return h


@router.put("/{hackathon_id}", response_model=HackathonResponse)
def update_hackathon(hackathon_id: str, body: HackathonUpdate, db: Session = Depends(get_db)):
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")
    if body.name is not None:
        h.name = body.name
    if body.config is not None:
        h.config = body.config
    db.commit()
    db.refresh(h)
    return h


@router.delete("/{hackathon_id}", status_code=204)
def delete_hackathon(hackathon_id: str, db: Session = Depends(get_db)):
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")

    h_dir = storage.hackathon_dir(hackathon_id)
    if h_dir.exists():
        shutil.rmtree(h_dir, ignore_errors=True)

    db.delete(h)
    db.commit()


@router.post("/{hackathon_id}/csv", response_model=HackathonResponse)
async def upload_csv(hackathon_id: str, file: UploadFile, db: Session = Depends(get_db)):
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    storage.ensure_hackathon_dir(hackathon_id)
    dest = storage.csv_path(hackathon_id, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    h.csv_filename = file.filename
    db.commit()
    db.refresh(h)
    return h


@router.post("/{hackathon_id}/clear-cache", status_code=200)
def clear_hackathon_cache(hackathon_id: str, db: Session = Depends(get_db)):
    """Wipe all pipeline runs and cached run data (cloned repos, videos,
    reports, logs) for this hackathon. Preserves config and uploaded CSV.
    Refuses if a run is currently active.
    """
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")

    active = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.hackathon_id == hackathon_id,
            PipelineRun.status.in_(["pending", "running"]),
        )
        .first()
    )
    if active:
        raise HTTPException(
            409, f"Cannot clear cache while a run is {active.status} (id={active.id})"
        )

    deleted_rows = (
        db.query(PipelineRun)
        .filter(PipelineRun.hackathon_id == hackathon_id)
        .delete(synchronize_session=False)
    )
    db.commit()

    runs_dir = storage.hackathon_dir(hackathon_id) / "runs"
    if runs_dir.exists():
        shutil.rmtree(runs_dir, ignore_errors=True)

    return {"deleted_runs": deleted_rows}


@router.get("/{hackathon_id}/csv/preview")
def preview_csv(
    hackathon_id: str,
    limit: int = Query(default=10, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return a slice of the uploaded CSV for paginated preview."""
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")
    if not h.csv_filename:
        raise HTTPException(404, "No CSV uploaded")

    path = storage.csv_path(hackathon_id, h.csv_filename)
    if not path.exists():
        raise HTTPException(404, "CSV file missing on disk")

    headers: list[str] = []
    rows: list[list[str]] = []
    total_rows = 0
    end = offset + limit
    with open(path, "r", encoding="utf-8", newline="", errors="replace") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            headers = []
        for i, row in enumerate(reader):
            total_rows += 1
            if offset <= i < end:
                rows.append(row)

    return {
        "filename": h.csv_filename,
        "headers": headers,
        "rows": rows,
        "total_rows": total_rows,
        "offset": offset,
        "limit": limit,
    }



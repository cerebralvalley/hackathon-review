"""CRUD endpoints for hackathons + CSV upload."""

from __future__ import annotations

import csv
import shutil

from fastapi import APIRouter, Depends, HTTPException, UploadFile
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


@router.get("/{hackathon_id}/csv-headers")
def get_csv_headers(hackathon_id: str, db: Session = Depends(get_db)):
    """Return column headers from the uploaded CSV for mapping UI."""
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")
    if not h.csv_filename:
        raise HTTPException(400, "No CSV uploaded")

    csv_file = storage.csv_path(hackathon_id, h.csv_filename)
    if not csv_file.exists():
        raise HTTPException(404, "CSV file not found on disk")

    with open(csv_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip().rstrip(",")
            if not stripped or "," not in stripped:
                continue
            reader = csv.reader([line])
            headers = next(reader)
            return {"headers": [h.strip() for h in headers if h.strip()]}

    return {"headers": []}

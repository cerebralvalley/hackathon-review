"""CRUD endpoints for hackathons + CSV upload."""

from __future__ import annotations

import csv
import io
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
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
    # Also wipe the hackathon-level shared cache (cloned repos + videos +
    # cached LLM analysis) so the next run starts from a fully clean slate.
    repos_dir = storage.hackathon_repos_dir(hackathon_id)
    if repos_dir.exists():
        shutil.rmtree(repos_dir, ignore_errors=True)
    videos_dir = storage.hackathon_videos_dir(hackathon_id)
    if videos_dir.exists():
        shutil.rmtree(videos_dir, ignore_errors=True)
    llm_cache_dir = storage.hackathon_dir(hackathon_id) / "cache"
    if llm_cache_dir.exists():
        shutil.rmtree(llm_cache_dir, ignore_errors=True)

    return {"deleted_runs": deleted_rows}


class SubmissionUpdate(BaseModel):
    github_url: str | None = None
    video_url: str | None = None


def _resolve_column(
    field: str,
    cfg_columns: dict,
    headers: list[str],
) -> str | None:
    """Resolve a column name from configured mapping, then auto-detect aliases."""
    from hackathon_reviewer.stages.parse import _auto_detect_columns
    configured = cfg_columns.get(field)
    if configured and configured in headers:
        return configured
    auto = _auto_detect_columns(headers)
    return auto.get(field)


@router.patch("/{hackathon_id}/submissions/{team_number}")
def update_submission_urls(
    hackathon_id: str,
    team_number: int,
    body: SubmissionUpdate,
    db: Session = Depends(get_db),
):
    """Edit the GitHub URL or video URL for a single team in the uploaded CSV.

    Useful when an organizer is doing outreach: a team submits a wrong URL,
    you ask them for the right one over email, and you want to fix it
    without re-exporting the CSV. Updates are written back to the canonical
    CSV file on disk and the new URLs are re-classified so the response
    immediately tells you whether the new value is valid (and if not, why).

    To pick up the new URLs in the rest of the pipeline, re-run the
    pipeline. The hackathon-level shared cache means only the changed
    teams re-clone / re-download / re-LLM.
    """
    h = db.get(Hackathon, hackathon_id)
    if not h:
        raise HTTPException(404, "Hackathon not found")
    if not h.csv_filename:
        raise HTTPException(400, "No CSV uploaded")
    if body.github_url is None and body.video_url is None:
        raise HTTPException(400, "Provide github_url and/or video_url")

    csv_file = storage.csv_path(hackathon_id, h.csv_filename)
    if not csv_file.exists():
        raise HTTPException(404, "CSV file missing on disk")

    from hackathon_reviewer.stages.parse import (
        _find_header_row,
        classify_github_url,
        classify_video_url,
    )

    # Preserve any pre-header lines verbatim (e.g. "PROJECTS TABLE" labels).
    with open(csv_file, "r", encoding="utf-8", newline="") as f:
        raw_lines = f.readlines()
    skip_rows = _find_header_row(csv_file)
    prefix_lines = raw_lines[:skip_rows]
    csv_text = "".join(raw_lines[skip_rows:])

    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)

    if team_number < 1 or team_number > len(rows):
        raise HTTPException(404, f"Team #{team_number} not found in CSV")

    cfg_columns = (h.config or {}).get("columns", {}) or {}
    github_col = _resolve_column("github_url", cfg_columns, fieldnames)
    video_col = _resolve_column("video_url", cfg_columns, fieldnames)

    target = rows[team_number - 1]
    if body.github_url is not None:
        if not github_col:
            raise HTTPException(400, "No GitHub URL column found in this CSV")
        target[github_col] = body.github_url
    if body.video_url is not None:
        if not video_col:
            raise HTTPException(400, "No video URL column found in this CSV")
        target[video_col] = body.video_url

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    new_text = out.getvalue()

    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        f.writelines(prefix_lines)
        f.write(new_text)

    new_github = (
        classify_github_url(body.github_url) if body.github_url is not None else None
    )
    new_video = (
        classify_video_url(body.video_url) if body.video_url is not None else None
    )

    # Also patch the latest run's submissions.json in place so the per-team
    # Retry button (which reads that file) picks up the new URL without
    # waiting for the user to trigger a fresh pipeline run that re-parses
    # the CSV from scratch.
    _patch_latest_run_submissions(
        db, hackathon_id, team_number, new_github, new_video
    )

    response: dict = {"team_number": team_number}
    if new_github is not None:
        response["github"] = new_github.model_dump(mode="json")
    if new_video is not None:
        response["video"] = new_video.model_dump(mode="json")
    return response


def _patch_latest_run_submissions(
    db,
    hackathon_id: str,
    team_number: int,
    new_github,
    new_video,
) -> None:
    """Patch the team's URL across every run for this hackathon.

    Outreach prefers the most recent *completed* run, while the active
    pipeline writes to the most recent *interrupted/running* run. We don't
    know in advance which run the user is currently viewing, so update
    them all — and clear the stale per-run download/clone artifacts in
    each so Outreach reflects the fresh state immediately.
    """
    import json
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.hackathon_id == hackathon_id)
        .order_by(PipelineRun.created_at.desc())
        .all()
    )
    if not runs:
        return

    for run in runs:
        run_data = storage.run_data_dir(hackathon_id, run.id)
        subs_path = run_data / "submissions.json"
        if not subs_path.exists():
            continue
        try:
            with open(subs_path, "r", encoding="utf-8") as f:
                subs = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(subs, list):
            continue
        sanitized: str | None = None
        changed = False
        for entry in subs:
            if entry.get("team_number") != team_number:
                continue
            sanitized = entry.get("sanitized_name") or None
            if new_github is not None:
                entry["github"] = new_github.model_dump(mode="json")
                changed = True
            if new_video is not None:
                entry["video"] = new_video.model_dump(mode="json")
                changed = True
            break
        if changed:
            with open(subs_path, "w", encoding="utf-8") as f:
                json.dump(subs, f, indent=2, ensure_ascii=False)

        if new_video is not None:
            _purge_team_video(run_data, hackathon_id, team_number, sanitized)
        if new_github is not None:
            _purge_team_clone(run_data, hackathon_id, team_number, sanitized)


def _drop_team_from_list(path, team_number: int) -> None:
    import json
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, list):
        return
    filtered = [e for e in data if e.get("team_number") != team_number]
    if len(filtered) != len(data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2, ensure_ascii=False)


def _drop_team_from_dict(path, team_number: int) -> None:
    import json
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    key = str(team_number)
    if key in data:
        del data[key]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def _purge_team_video(run_data, hackathon_id: str, team_number: int, sanitized: str | None) -> None:
    if sanitized:
        videos_dir = storage.hackathon_videos_dir(hackathon_id)
        for name in (f"{sanitized}.mp4", f"{sanitized}_prepared.mp4"):
            (videos_dir / name).unlink(missing_ok=True)
    _drop_team_from_dict(run_data / "video_downloads.json", team_number)
    _drop_team_from_list(run_data / "video_analysis.json", team_number)


def _purge_team_clone(run_data, hackathon_id: str, team_number: int, sanitized: str | None) -> None:
    if sanitized:
        repo_dir = storage.hackathon_repos_dir(hackathon_id) / sanitized
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
    _drop_team_from_list(run_data / "repo_metadata.json", team_number)
    _drop_team_from_list(run_data / "static_analysis.json", team_number)
    _drop_team_from_list(run_data / "code_reviews.json", team_number)


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



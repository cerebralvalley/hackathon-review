"""Bridge between the API and the hackathon_reviewer pipeline stages."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from api.app import models as db_models
from api.app.services import storage

logger = logging.getLogger(__name__)

STAGE_ORDER = [
    "parse",
    "clone",
    "video_download",
    "static_analysis",
    "code_review",
    "video_analysis",
    "scoring",
    "reporting",
]


def _build_review_config(
    hackathon: db_models.Hackathon,
    run: db_models.PipelineRun,
) -> "ReviewConfig":
    """Build a ReviewConfig from DB hackathon config + run output dir."""
    from hackathon_reviewer.config import ReviewConfig

    config_dict = dict(hackathon.config or {})
    cfg = ReviewConfig(**config_dict)

    csv_file = storage.csv_path(hackathon.id, hackathon.csv_filename or "")
    cfg.csv_path = csv_file if csv_file.exists() else None

    output_dir = storage.run_output_dir(hackathon.id, run.id)
    cfg.output_dir = output_dir
    cfg.ensure_dirs()

    return cfg


def _update_run(db: Session, run: db_models.PipelineRun, **kwargs) -> None:
    for k, v in kwargs.items():
        setattr(run, k, v)
    db.commit()
    db.refresh(run)


def execute_pipeline(db: Session, run_id: str, resume: bool = True) -> None:
    """Run the full pipeline for a given PipelineRun. Called in a background thread."""
    run = db.get(db_models.PipelineRun, run_id)
    if not run:
        logger.error("PipelineRun %s not found", run_id)
        return

    hackathon = run.hackathon
    if not hackathon:
        _update_run(db, run, status="failed", error="Hackathon not found")
        return

    if not hackathon.csv_filename:
        _update_run(db, run, status="failed", error="No CSV uploaded")
        return

    _update_run(
        db, run,
        status="running",
        started_at=datetime.now(timezone.utc),
        stage_progress={s: "pending" for s in STAGE_ORDER},
    )

    try:
        cfg = _build_review_config(hackathon, run)
    except Exception as exc:
        _update_run(db, run, status="failed", error=f"Config error: {exc}")
        return

    try:
        _run_stages(db, run, cfg, resume)
    except Exception as exc:
        logger.exception("Pipeline failed for run %s", run_id)
        progress = dict(run.stage_progress or {})
        if run.current_stage:
            progress[run.current_stage] = "failed"
        _update_run(
            db, run,
            status="failed",
            error=traceback.format_exc()[-500:],
            stage_progress=progress,
            completed_at=datetime.now(timezone.utc),
        )


def _run_stages(
    db: Session,
    run: db_models.PipelineRun,
    cfg: "ReviewConfig",
    resume: bool,
) -> None:
    from hackathon_reviewer.stages.parse import run_parse
    from hackathon_reviewer.stages.clone import run_clone
    from hackathon_reviewer.stages.video import run_video_download
    from hackathon_reviewer.stages.static_analysis import run_static_analysis
    from hackathon_reviewer.stages.code_review import run_code_review
    from hackathon_reviewer.stages.video_analysis import run_video_analysis
    from hackathon_reviewer.stages.scoring import run_scoring
    from hackathon_reviewer.stages.reporting import run_reporting

    def _mark(stage: str, status: str) -> None:
        progress = dict(run.stage_progress or {})
        progress[stage] = status
        updates = {"stage_progress": progress}
        if status == "running":
            updates["current_stage"] = stage
        _update_run(db, run, **updates)

    # Stage 1: Parse
    _mark("parse", "running")
    submissions = run_parse(cfg)
    _mark("parse", "completed")

    # Stage 2: Clone
    _mark("clone", "running")
    repo_metadata = run_clone(cfg, submissions, resume=resume)
    _mark("clone", "completed")

    # Stage 3: Video download
    _mark("video_download", "running")
    video_downloads = run_video_download(cfg, submissions, resume=resume)
    _mark("video_download", "completed")

    # Stage 4: Static analysis
    _mark("static_analysis", "running")
    static_results = run_static_analysis(cfg, submissions, repo_metadata)
    _mark("static_analysis", "completed")

    # Stage 5: Code review
    _mark("code_review", "running")
    code_reviews = run_code_review(cfg, submissions, repo_metadata, static_results, resume=resume)
    _mark("code_review", "completed")

    # Stage 6: Video analysis
    _mark("video_analysis", "running")
    video_results = run_video_analysis(cfg, submissions, video_downloads, resume=resume)
    _mark("video_analysis", "completed")

    # Stage 7: Scoring
    _mark("scoring", "running")
    scores = run_scoring(cfg, submissions, repo_metadata, static_results, code_reviews, video_results)
    _mark("scoring", "completed")

    # Stage 8: Reporting
    _mark("reporting", "running")
    run_reporting(cfg, submissions, repo_metadata, static_results, code_reviews, video_results, scores)
    _mark("reporting", "completed")

    _update_run(
        db, run,
        status="completed",
        current_stage=None,
        completed_at=datetime.now(timezone.utc),
    )

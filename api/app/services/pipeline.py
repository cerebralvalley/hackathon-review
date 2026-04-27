"""Bridge between the API and the hackathon_reviewer pipeline stages."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from api.app import models as db_models
from api.app.services import storage
from api.app.services.log_capture import capture_stage

logger = logging.getLogger(__name__)


class PipelineCancelled(Exception):
    """Raised cooperatively when the user clicks Stop on a running pipeline."""


class StageProgress:
    """Accumulates progress and failures for a single stage, flushing to the DB.

    `update`/`add_failure` are the natural cancel-check points — they're called
    once per team in the long stages (clone, video_download, code_review,
    video_analysis), so a stop request takes effect within ~one team's worth
    of latency.
    """

    def __init__(self, stage: str, db: "Session", run: "db_models.PipelineRun"):
        self._stage = stage
        self._db = db
        self._run = run
        self.done = 0
        self.total = 0
        self.failures: list[dict] = []

    def update(self, done: int, total: int, message: str = "") -> None:
        self.done = done
        self.total = total
        self._flush(message)
        self._check_cancel()

    def add_failure(self, team_number: int, team_name: str, project_name: str, error: str) -> None:
        self.failures.append({
            "team_number": team_number,
            "team_name": team_name,
            "project_name": project_name,
            "error": error,
        })
        self._flush()
        self._check_cancel()

    def _check_cancel(self) -> None:
        # Re-read the row so we see updates from the request thread.
        self._db.refresh(self._run)
        if self._run.cancel_requested:
            raise PipelineCancelled()

    def _flush(self, message: str = "") -> None:
        detail = dict(self._run.stage_detail or {})
        detail[self._stage] = {
            "done": self.done,
            "total": self.total,
            "message": message,
            "failures": self.failures,
        }
        _update_run(self._db, self._run, stage_detail=detail)

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
    """Build a ReviewConfig from DB hackathon config + run output dir.

    Web mode: repos and videos are pinned to a hackathon-level shared
    cache so subsequent pipeline runs reuse already-cloned repos and
    already-downloaded videos. Per-run output (data/, reports/, logs/)
    still lives under runs/<run_id>/.
    """
    from hackathon_reviewer.config import ReviewConfig

    config_dict = dict(hackathon.config or {})
    cfg = ReviewConfig(**config_dict)

    csv_file = storage.csv_path(hackathon.id, hackathon.csv_filename or "")
    cfg.csv_path = csv_file if csv_file.exists() else None

    output_dir = storage.run_output_dir(hackathon.id, run.id)
    cfg.output_dir = output_dir
    cfg.repos_dir_override = storage.hackathon_repos_dir(hackathon.id)
    cfg.videos_dir_override = storage.hackathon_videos_dir(hackathon.id)
    cfg.cache_dir_override = storage.hackathon_dir(hackathon.id) / "cache"
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

    existing_progress = run.stage_progress or {}
    stage_progress = {}
    for s in STAGE_ORDER:
        if existing_progress.get(s) == "completed":
            stage_progress[s] = "completed"
        else:
            stage_progress[s] = "pending"

    _update_run(
        db, run,
        status="running",
        started_at=run.started_at or datetime.now(timezone.utc),
        stage_progress=stage_progress,
        cancel_requested=False,
    )

    try:
        cfg = _build_review_config(hackathon, run)
    except Exception as exc:
        _update_run(db, run, status="failed", error=f"Config error: {exc}")
        return

    try:
        _run_stages(db, run, cfg, resume)
    except PipelineCancelled:
        logger.info("Pipeline cancelled by user for run %s", run_id)
        progress = dict(run.stage_progress or {})
        if run.current_stage and progress.get(run.current_stage) == "running":
            progress[run.current_stage] = "interrupted"
        _update_run(
            db, run,
            status="interrupted",
            stage_progress=progress,
            completed_at=datetime.now(timezone.utc),
            cancel_requested=False,
        )
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
    from hackathon_reviewer.stages.parse import run_parse, load_submissions
    from hackathon_reviewer.stages.clone import run_clone, load_repo_metadata
    from hackathon_reviewer.stages.video import run_video_download, load_video_downloads
    from hackathon_reviewer.stages.static_analysis import run_static_analysis, load_static_analysis
    from hackathon_reviewer.stages.code_review import run_code_review, load_code_reviews
    from hackathon_reviewer.stages.video_analysis import run_video_analysis, load_video_analysis
    from hackathon_reviewer.stages.scoring import run_scoring, load_scores
    from hackathon_reviewer.stages.reporting import run_reporting

    prior = run.stage_progress or {}

    def _done(stage: str) -> bool:
        return prior.get(stage) == "completed"

    def _mark(stage: str, status: str) -> None:
        progress = dict(run.stage_progress or {})
        progress[stage] = status
        updates = {"stage_progress": progress}
        if status == "running":
            updates["current_stage"] = stage
        _update_run(db, run, **updates)

    def _progress(stage: str) -> StageProgress:
        return StageProgress(stage, db, run)

    def _log_path(stage: str) -> Path:
        return storage.run_logs_dir(run.hackathon_id, run.id) / f"{stage}.log"

    # Stage 1: Parse
    if _done("parse"):
        logger.info("Skipping parse (already completed)")
        submissions = load_submissions(cfg)
    else:
        _mark("parse", "running")
        with capture_stage(_log_path("parse"), "parse"):
            submissions = run_parse(cfg)
        _mark("parse", "completed")

    # Stage 2: Clone
    if _done("clone"):
        logger.info("Skipping clone (already completed)")
        repo_metadata = load_repo_metadata(cfg)
    else:
        _mark("clone", "running")
        with capture_stage(_log_path("clone"), "clone"):
            repo_metadata = run_clone(cfg, submissions, resume=resume, progress=_progress("clone"))
        _mark("clone", "completed")

    # Stage 3: Video download
    if _done("video_download"):
        logger.info("Skipping video_download (already completed)")
        video_downloads = load_video_downloads(cfg)
    else:
        _mark("video_download", "running")
        with capture_stage(_log_path("video_download"), "video_download"):
            video_downloads = run_video_download(cfg, submissions, resume=resume, progress=_progress("video_download"))
        _mark("video_download", "completed")

    # Stage 4: Static analysis
    if _done("static_analysis"):
        logger.info("Skipping static_analysis (already completed)")
        static_results = load_static_analysis(cfg)
    else:
        _mark("static_analysis", "running")
        with capture_stage(_log_path("static_analysis"), "static_analysis"):
            static_results = run_static_analysis(cfg, submissions, repo_metadata, progress=_progress("static_analysis"))
        _mark("static_analysis", "completed")

    # Stage 5: Code review
    if _done("code_review"):
        logger.info("Skipping code_review (already completed)")
        code_reviews = load_code_reviews(cfg)
    else:
        _mark("code_review", "running")
        with capture_stage(_log_path("code_review"), "code_review"):
            code_reviews = run_code_review(cfg, submissions, repo_metadata, static_results, resume=resume, progress=_progress("code_review"))
        _mark("code_review", "completed")

    # Stage 6: Video analysis
    if _done("video_analysis"):
        logger.info("Skipping video_analysis (already completed)")
        video_results = load_video_analysis(cfg)
    else:
        _mark("video_analysis", "running")
        with capture_stage(_log_path("video_analysis"), "video_analysis"):
            video_results = run_video_analysis(cfg, submissions, video_downloads, resume=resume, progress=_progress("video_analysis"))
        _mark("video_analysis", "completed")

    # Stage 7: Scoring
    if _done("scoring"):
        logger.info("Skipping scoring (already completed)")
        scores = load_scores(cfg)
    else:
        _mark("scoring", "running")
        with capture_stage(_log_path("scoring"), "scoring"):
            scores = run_scoring(cfg, submissions, repo_metadata, static_results, code_reviews, video_results, progress=_progress("scoring"))
        _mark("scoring", "completed")

    # Stage 8: Reporting (always re-run to pick up any changes)
    _mark("reporting", "running")
    with capture_stage(_log_path("reporting"), "reporting"):
        run_reporting(cfg, submissions, repo_metadata, static_results, code_reviews, video_results, scores, progress=_progress("reporting"))
    _mark("reporting", "completed")

    _update_run(
        db, run,
        status="completed",
        current_stage=None,
        completed_at=datetime.now(timezone.utc),
    )

"""Retry individual failed items within a completed/failed pipeline run."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from api.app import models as db_models
from api.app.services import storage
from api.app.services.pipeline import _build_review_config, _update_run

logger = logging.getLogger(__name__)


def retry_items(
    db: Session,
    run_id: str,
    stage: str,
    team_numbers: list[int],
) -> None:
    run = db.get(db_models.PipelineRun, run_id)
    if not run or not run.hackathon:
        return

    try:
        cfg = _build_review_config(run.hackathon, run)
    except Exception:
        logger.exception("Failed to build config for retry")
        return

    detail = dict(run.stage_detail or {})
    # Make a *new* inner dict so SQLAlchemy sees stage_detail as changed.
    # Mutating detail[stage] in place would alias the original column value
    # and the change wouldn't be persisted on commit.
    stage_info = dict(detail.get(stage, {}))
    failures_before = stage_info.get("failures", [])
    team_set = set(team_numbers)

    if stage == "clone":
        _retry_clone(cfg, team_numbers)
    elif stage == "video_download":
        _retry_video_download(cfg, team_numbers)
    elif stage == "code_review":
        _retry_code_review(cfg, team_numbers)
    elif stage == "video_analysis":
        _retry_video_analysis(cfg, team_numbers)
    else:
        return

    remaining_failures = [f for f in failures_before if f["team_number"] not in team_set]
    stage_info["failures"] = remaining_failures
    detail[stage] = stage_info
    _update_run(db, run, stage_detail=detail)


def _retry_clone(cfg, team_numbers: list[int]) -> None:
    import shutil
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.clone import _process_one, _load_metadata_file

    submissions = load_submissions(cfg)
    sub_map = {s.team_number: s for s in submissions}

    out_path = cfg.data_dir / "repo_metadata.json"
    existing = {m.team_number: m for m in _load_metadata_file(out_path)} if out_path.exists() else {}

    from hackathon_reviewer.utils.cache_key import repo_cache_key
    for tn in team_numbers:
        sub = sub_map.get(tn)
        if not sub:
            continue
        # Wipe both the new (URL-hash) path and the legacy (sanitized_name)
        # path so a fresh clone is forced.
        for d in (cfg.repos_dir / repo_cache_key(sub), cfg.repos_dir / sub.sanitized_name):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        meta = _process_one(sub, cfg)
        existing[tn] = meta
        logger.info("Retry clone team %d: success=%s", tn, meta.clone_success)

    ordered = [existing.get(s.team_number, existing[s.team_number]) for s in submissions if s.team_number in existing]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([m.model_dump(mode="json") for m in ordered], f, indent=2, ensure_ascii=False)


def _retry_video_download(cfg, team_numbers: list[int]) -> None:
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.video import _download_one, _load_downloads_file

    submissions = load_submissions(cfg)
    sub_map = {s.team_number: s for s in submissions}

    out_path = cfg.data_dir / "video_downloads.json"
    existing = _load_downloads_file(out_path) if out_path.exists() else {}

    from hackathon_reviewer.utils.cache_key import video_cache_key
    for tn in team_numbers:
        sub = sub_map.get(tn)
        if not sub:
            continue
        # Wipe both the new (URL-hash) path and the legacy (sanitized_name)
        # path so a fresh download is forced.
        for name in (
            f"{video_cache_key(sub)}.mp4",
            f"{video_cache_key(sub)}_prepared.mp4",
            f"{sub.sanitized_name}.mp4",
            f"{sub.sanitized_name}_prepared.mp4",
        ):
            (cfg.videos_dir / name).unlink(missing_ok=True)
        _, result = _download_one(sub, cfg)
        existing[tn] = result
        logger.info("Retry video download team %d: success=%s", tn, result.success)

    serializable = {str(k): v.model_dump(mode="json") for k, v in existing.items()}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)


def _retry_code_review(cfg, team_numbers: list[int]) -> None:
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.clone import load_repo_metadata
    from hackathon_reviewer.stages.static_analysis import load_static_analysis
    from hackathon_reviewer.stages.code_review import _review_one, _build_provider, _load_reviews_file, _save_reviews

    submissions = load_submissions(cfg)
    sub_map = {s.team_number: s for s in submissions}
    meta_map = {m.team_number: m for m in load_repo_metadata(cfg)}
    static_map = {s.team_number: s for s in load_static_analysis(cfg)}

    out_path = cfg.data_dir / "code_reviews.json"
    existing = {r.team_number: r for r in _load_reviews_file(out_path)} if out_path.exists() else {}

    provider = _build_provider(cfg)
    for tn in team_numbers:
        sub = sub_map.get(tn)
        meta = meta_map.get(tn)
        static = static_map.get(tn)
        if not sub or not meta or not static:
            continue
        result = _review_one(provider, sub, meta, static, cfg)
        existing[tn] = result
        logger.info("Retry code review team %d: success=%s", tn, result.success)

    ordered = [existing[s.team_number] for s in submissions if s.team_number in existing]
    _save_reviews(ordered, out_path)


def _retry_video_analysis(cfg, team_numbers: list[int]) -> None:
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.video import load_video_downloads
    from hackathon_reviewer.stages.video_analysis import (
        _analyze_one, _build_provider, _load_analysis_file, _save_analysis,
    )

    submissions = load_submissions(cfg)
    sub_map = {s.team_number: s for s in submissions}
    downloads = load_video_downloads(cfg)

    out_path = cfg.data_dir / "video_analysis.json"
    existing = {r.team_number: r for r in _load_analysis_file(out_path)} if out_path.exists() else {}

    provider = _build_provider(cfg)
    for tn in team_numbers:
        sub = sub_map.get(tn)
        download = downloads.get(tn)
        if not sub or not download:
            continue
        from hackathon_reviewer.models import VideoDownloadResult
        result = _analyze_one(provider, sub, download, cfg)
        existing[tn] = result
        logger.info("Retry video analysis team %d: success=%s", tn, result.analysis_success)

    ordered = [existing[s.team_number] for s in submissions if s.team_number in existing]
    _save_analysis(ordered, out_path)

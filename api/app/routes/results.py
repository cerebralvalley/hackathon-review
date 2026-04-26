"""Result endpoints: leaderboard, project detail, flags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.app.database import get_db
from api.app.models import PipelineRun
from api.app.schemas import FlagResponse, LeaderboardEntry, ProjectSummary
from api.app.services import storage

router = APIRouter(prefix="/api/runs/{run_id}/results", tags=["results"])


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _get_run_or_404(run_id: str, db: Session) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


def _data_dir(run: PipelineRun) -> Path:
    return storage.run_data_dir(run.hackathon_id, run.id)


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(run_id: str, db: Session = Depends(get_db)):
    run = _get_run_or_404(run_id, db)
    data = _data_dir(run)

    scores = _load_json(data / "scores.json")
    if not scores:
        return []

    submissions = {s["team_number"]: s for s in _load_json(data / "submissions.json")}
    repo_meta = {m["team_number"]: m for m in _load_json(data / "repo_metadata.json")}
    static = {s["team_number"]: s for s in _load_json(data / "static_analysis.json")}

    sorted_scores = sorted(scores, key=lambda s: s.get("weighted_total", 0), reverse=True)

    entries = []
    for rank, ps in enumerate(sorted_scores, 1):
        tn = ps["team_number"]
        sub = submissions.get(tn, {})
        meta = repo_meta.get(tn, {})
        st = static.get(tn, {})

        criterion_scores = {}
        for crit_name, crit_data in ps.get("scores", {}).items():
            if isinstance(crit_data, dict):
                criterion_scores[crit_name] = crit_data.get("score", 0)
            else:
                criterion_scores[crit_name] = float(crit_data)

        files = meta.get("files", {})
        git = meta.get("git_history", {})

        entries.append(LeaderboardEntry(
            rank=rank,
            team_number=tn,
            team_name=ps.get("team_name", ""),
            project_name=ps.get("project_name", ""),
            weighted_total=ps.get("weighted_total", 0),
            scores=criterion_scores,
            total_loc=files.get("total_loc", 0),
            primary_language=files.get("primary_language", "unknown"),
            commits=git.get("total_commits", 0),
            integration_depth=st.get("integration_depth", "none"),
            github_url=sub.get("github", {}).get("original", ""),
            video_url=sub.get("video", {}).get("original", ""),
        ))

    return entries


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(run_id: str, db: Session = Depends(get_db)):
    run = _get_run_or_404(run_id, db)
    data = _data_dir(run)

    submissions = _load_json(data / "submissions.json")
    scores_map = {s["team_number"]: s for s in _load_json(data / "scores.json")}

    results = []
    for sub in submissions:
        tn = sub["team_number"]
        ps = scores_map.get(tn, {})
        results.append(ProjectSummary(
            team_number=tn,
            team_name=sub.get("team_name", ""),
            project_name=sub.get("project_name", ""),
            weighted_total=ps.get("weighted_total", 0),
        ))
    return results


@router.get("/projects/{team_number}")
def get_project(run_id: str, team_number: int, db: Session = Depends(get_db)):
    """Return all data for a single project, assembled from stage JSON files."""
    run = _get_run_or_404(run_id, db)
    data = _data_dir(run)

    def _find(items: list[dict], tn: int) -> dict | None:
        for item in items:
            if item.get("team_number") == tn:
                return item
        return None

    submission = _find(_load_json(data / "submissions.json"), team_number)
    if not submission:
        raise HTTPException(404, "Project not found")

    return {
        "submission": submission,
        "repo_metadata": _find(_load_json(data / "repo_metadata.json"), team_number),
        "static_analysis": _find(_load_json(data / "static_analysis.json"), team_number),
        "code_review": _find(_load_json(data / "code_reviews.json"), team_number),
        "video_analysis": _find(_load_json(data / "video_analysis.json"), team_number),
        "score": _find(_load_json(data / "scores.json"), team_number),
    }


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

@router.get("/flags", response_model=list[FlagResponse])
def get_flags(run_id: str, db: Session = Depends(get_db)):
    """Recompute flags from stage data (same logic as reporting stage)."""
    run = _get_run_or_404(run_id, db)
    data = _data_dir(run)

    submissions = _load_json(data / "submissions.json")
    repo_meta = {m["team_number"]: m for m in _load_json(data / "repo_metadata.json")}
    video_results = {v["team_number"]: v for v in _load_json(data / "video_analysis.json")}

    hackathon_cfg = (run.hackathon.config or {}).get("hackathon", {}) if run.hackathon else {}
    max_team_size = hackathon_cfg.get("max_team_size")
    tolerance = int(hackathon_cfg.get("contributor_tolerance", 0) or 0)

    flags: list[FlagResponse] = []

    for sub in submissions:
        tn = sub["team_number"]
        team = sub.get("team_name", "")
        project = sub.get("project_name", "")
        gh = sub.get("github", {})
        vid = sub.get("video", {})
        meta = repo_meta.get(tn, {})
        video = video_results.get(tn, {})

        if not gh.get("is_valid"):
            issues = ", ".join(gh.get("issues", []))
            flags.append(FlagResponse(
                team_number=tn, team_name=team, project_name=project,
                flag_type="invalid_github_url",
                description=f"GitHub URL invalid: {issues}",
                severity="error",
            ))
        elif meta and not meta.get("clone_success"):
            flags.append(FlagResponse(
                team_number=tn, team_name=team, project_name=project,
                flag_type="clone_failed",
                description=f"Could not clone repo: {meta.get('clone_error', '')}",
                severity="error",
            ))

        if not vid.get("is_valid"):
            issues = ", ".join(vid.get("issues", []))
            flags.append(FlagResponse(
                team_number=tn, team_name=team, project_name=project,
                flag_type="invalid_video_url",
                description=f"Video URL invalid: {issues}",
                severity="error",
            ))
        elif video:
            dl = video.get("download", {})
            if not dl.get("success"):
                flags.append(FlagResponse(
                    team_number=tn, team_name=team, project_name=project,
                    flag_type="video_download_failed",
                    description=f"Could not download video: {dl.get('error', '')}",
                    severity="error",
                ))

        if video.get("analysis_success") and not video.get("is_related_to_project", True):
            flags.append(FlagResponse(
                team_number=tn, team_name=team, project_name=project,
                flag_type="video_unrelated",
                description="Video does not appear related to the project",
                severity="warning",
            ))

        git_history = meta.get("git_history", {})
        period_flag = git_history.get("hackathon_period_flag", "unknown")
        if period_flag in ("significant_prior_work", "pre_existing_project"):
            before = git_history.get("commits_before_hackathon", 0)
            flags.append(FlagResponse(
                team_number=tn, team_name=team, project_name=project,
                flag_type="git_period_violation",
                description=f"Git history: {period_flag} ({before} commits before hackathon)",
                severity="warning",
            ))

        if git_history.get("is_single_commit_dump"):
            flags.append(FlagResponse(
                team_number=tn, team_name=team, project_name=project,
                flag_type="single_commit_dump",
                description="Repository has only a single commit",
                severity="info",
            ))

        # Contributor count check.
        contributor_count = git_history.get("human_contributor_count")
        if isinstance(contributor_count, int) and contributor_count > 0:
            listed_members = len(sub.get("members", []))
            limits: list[int] = []
            if listed_members > 0:
                limits.append(listed_members + tolerance)
            if isinstance(max_team_size, int) and max_team_size > 0:
                limits.append(max_team_size)
            if limits:
                cap = min(limits)
                if contributor_count > cap:
                    contributors = git_history.get("contributors", [])
                    names = ", ".join(
                        c.get("name") or c.get("email", "?") for c in contributors[:6]
                    )
                    if len(contributors) > 6:
                        names += f", +{len(contributors) - 6} more"
                    flags.append(FlagResponse(
                        team_number=tn, team_name=team, project_name=project,
                        flag_type="excessive_contributors",
                        description=(
                            f"{contributor_count} contributors (cap {cap}, "
                            f"{listed_members} listed): {names}"
                        ),
                        severity="warning",
                    ))

    return flags

"""Result endpoints: leaderboard, project detail, flags."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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


def _video_download_status(data: Path) -> dict[int, dict]:
    """Read video_downloads.json (the per-team download result map written by
    the video_download stage) and prefer it over video_analysis.json's nested
    download field. This way Flags / Outreach reflect download success/failure
    as soon as the download stage finishes — without waiting for the LLM
    analysis stage to also complete.
    """
    out: dict[int, dict] = {}
    # Primary source: video_downloads.json. Stage writes a dict keyed by
    # stringified team number → VideoDownloadResult dict.
    primary_path = data / "video_downloads.json"
    if primary_path.exists():
        try:
            with open(primary_path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            if isinstance(blob, dict):
                for k, v in blob.items():
                    try:
                        out[int(k)] = v if isinstance(v, dict) else {}
                    except (TypeError, ValueError):
                        continue
        except (OSError, json.JSONDecodeError):
            pass
    # Fallback / overlay: video_analysis.json's nested download field if
    # video_downloads.json hasn't been written or is missing teams.
    for v in _load_json(data / "video_analysis.json"):
        tn = v.get("team_number")
        dl = v.get("download")
        if isinstance(tn, int) and isinstance(dl, dict) and tn not in out:
            out[tn] = dl
    return out


_SUMMARY_RE = re.compile(r"^\*\*[^*]+:\*\*\s*(.+?)(?=\n\n\*\*|\Z)", re.DOTALL)


def _extract_summary(review_text: str | None) -> str:
    """Pull the first markdown section out of an LLM review_text.

    review_text starts with sections like ``**What it does:** <body>\n\n**Architecture:** ...``.
    The first section is a self-contained one-paragraph summary of the project,
    which is exactly what we want to surface in the leaderboard CSV.
    """
    if not review_text:
        return ""
    m = _SUMMARY_RE.match(review_text)
    body = m.group(1).strip() if m else review_text.strip()
    if len(body) > 500:
        body = body[:497].rstrip() + "..."
    return body


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
    reviews = {r["team_number"]: r for r in _load_json(data / "code_reviews.json")}

    sorted_scores = sorted(scores, key=lambda s: s.get("weighted_total", 0), reverse=True)

    entries = []
    for rank, ps in enumerate(sorted_scores, 1):
        tn = ps["team_number"]
        sub = submissions.get(tn, {})
        meta = repo_meta.get(tn, {})
        st = static.get(tn, {})
        review = reviews.get(tn, {})

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
            summary=_extract_summary(review.get("review_text")),
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

def _flag_key(team_number: int, flag_type: str) -> str:
    return f"{team_number}:{flag_type}"


@router.get("/flags", response_model=list[FlagResponse])
def get_flags(run_id: str, db: Session = Depends(get_db)):
    """Recompute flags from stage data (same logic as reporting stage)."""
    run = _get_run_or_404(run_id, db)
    data = _data_dir(run)

    submissions = _load_json(data / "submissions.json")
    repo_meta = {m["team_number"]: m for m in _load_json(data / "repo_metadata.json")}
    video_results = {v["team_number"]: v for v in _load_json(data / "video_analysis.json")}
    download_status = _video_download_status(data)

    hackathon_cfg = (run.hackathon.config or {}).get("hackathon", {}) if run.hackathon else {}
    max_team_size = hackathon_cfg.get("max_team_size")
    tolerance = int(hackathon_cfg.get("contributor_tolerance", 0) or 0)

    dismissed: set[str] = set(run.dismissed_flags or [])

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
        else:
            dl = download_status.get(tn) or (video.get("download") if video else None)
            if dl is not None and not dl.get("success"):
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

    for f in flags:
        f.dismissed = _flag_key(f.team_number, f.flag_type) in dismissed

    return flags


class FlagDismissBody(BaseModel):
    team_number: int
    flag_type: str


@router.post("/flags/dismiss", response_model=list[str])
def dismiss_flag(run_id: str, body: FlagDismissBody, db: Session = Depends(get_db)):
    """Mark a single flag as dismissed for this run. Idempotent."""
    run = _get_run_or_404(run_id, db)
    key = _flag_key(body.team_number, body.flag_type)
    current = list(run.dismissed_flags or [])
    if key not in current:
        current.append(key)
        run.dismissed_flags = current
        db.commit()
        db.refresh(run)
    return current


@router.post("/flags/undismiss", response_model=list[str])
def undismiss_flag(run_id: str, body: FlagDismissBody, db: Session = Depends(get_db)):
    """Restore a dismissed flag. Idempotent."""
    run = _get_run_or_404(run_id, db)
    key = _flag_key(body.team_number, body.flag_type)
    current = [k for k in (run.dismissed_flags or []) if k != key]
    if current != list(run.dismissed_flags or []):
        run.dismissed_flags = current
        db.commit()
        db.refresh(run)
    return current


# ---------------------------------------------------------------------------
# Outreach — failed submissions with team contact info, for organizers to
# email teams whose repos / videos couldn't be processed.
# ---------------------------------------------------------------------------

@router.get("/outreach")
def get_outreach(run_id: str, db: Session = Depends(get_db)):
    """Per-team breakdown of submissions that need organizer follow-up.

    A team appears here only if at least one of: invalid GitHub URL, clone
    failed, invalid video URL, or video download failed. Returns the team
    info, member emails, and the original URLs they submitted, so an
    organizer can email them directly.
    """
    run = _get_run_or_404(run_id, db)
    data = _data_dir(run)

    submissions = _load_json(data / "submissions.json")
    repo_meta = {m["team_number"]: m for m in _load_json(data / "repo_metadata.json")}
    video_results = {v["team_number"]: v for v in _load_json(data / "video_analysis.json")}
    download_status = _video_download_status(data)

    out = []
    for sub in submissions:
        tn = sub["team_number"]
        issues: list[dict] = []

        gh = sub.get("github", {})
        meta = repo_meta.get(tn, {})
        if not gh.get("is_valid"):
            details = ", ".join(gh.get("issues", [])) or "URL did not match GitHub format"
            issues.append({
                "type": "invalid_github_url",
                "label": "GitHub URL invalid",
                "description": details,
            })
        elif meta and not meta.get("clone_success"):
            issues.append({
                "type": "clone_failed",
                "label": "Repo clone failed",
                "description": meta.get("clone_error") or "Could not clone repository",
            })

        vid = sub.get("video", {})
        video = video_results.get(tn, {})
        if not vid.get("is_valid"):
            details = ", ".join(vid.get("issues", [])) or "URL did not match a known video host"
            issues.append({
                "type": "invalid_video_url",
                "label": "Video URL invalid",
                "description": details,
            })
        else:
            dl = download_status.get(tn) or (video.get("download") if video else None)
            if dl is not None and not dl.get("success"):
                issues.append({
                    "type": "video_download_failed",
                    "label": "Video download failed",
                    "description": dl.get("error") or "Could not download video",
                })

        if not issues:
            continue

        out.append({
            "team_number": tn,
            "team_name": sub.get("team_name", ""),
            "project_name": sub.get("project_name", ""),
            "members": sub.get("members", []),
            "issues": issues,
            "github_url": gh.get("original", ""),
            "video_url": vid.get("original", ""),
        })

    return out

"""Stage 1: Parse submissions CSV into structured data."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import click

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    GitHubInfo,
    LatenessCategory,
    Submission,
    TeamMember,
    TimingInfo,
    VideoInfo,
    VideoPlatform,
)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def classify_github_url(raw_url: str) -> GitHubInfo:
    url = raw_url.strip()
    info = GitHubInfo(original=url)

    if not url:
        info.issues.append("empty_url")
        return info

    url = url.replace("https:www.github.com", "https://www.github.com")
    url = url.replace("www.github.com", "github.com")

    parsed = urlparse(url)
    if "github.com" not in parsed.netloc and "github.com" not in parsed.path:
        info.issues.append(f"not_github_url: {parsed.netloc}")
        info.cleaned = url
        return info

    if not url.startswith("http"):
        url = "https://" + url

    info.cleaned = url

    clone_url = re.sub(r"/tree/.*$", "", url)
    clone_url = re.sub(r"/blob/.*$", "", url)
    clone_url = clone_url.rstrip("/")

    if "github.io" in url:
        info.issues.append("github_pages_not_repo")
        return info

    info.clone_url = clone_url + ".git"
    info.is_valid = True

    if "/tree/" in raw_url or "/blob/" in raw_url:
        info.issues.append("stripped_branch_ref")

    return info


def classify_video_url(raw_url: str) -> VideoInfo:
    url = raw_url.strip()
    info = VideoInfo(original=url)

    if not url:
        info.issues.append("empty_url")
        return info

    lower = url.lower()

    platform_checks: list[tuple[list[str], VideoPlatform]] = [
        (["youtu.be", "youtube.com"], VideoPlatform.YOUTUBE),
        (["loom.com"], VideoPlatform.LOOM),
        (["vimeo.com"], VideoPlatform.VIMEO),
        (["drive.google.com", "docs.google.com/video"], VideoPlatform.GOOGLE_DRIVE),
        (["dropbox.com"], VideoPlatform.DROPBOX),
        (["descript.com"], VideoPlatform.DESCRIPT),
        (["screen.studio"], VideoPlatform.SCREEN_STUDIO),
    ]

    for keywords, platform in platform_checks:
        if any(kw in lower for kw in keywords):
            info.platform = platform
            info.is_valid = True
            break
    else:
        if "example.com" in lower:
            info.platform = VideoPlatform.UNKNOWN
            info.issues.append("placeholder_url")
        elif url.startswith("http"):
            info.platform = VideoPlatform.CUSTOM
            info.is_valid = True
            info.issues.append("custom_domain_may_not_be_downloadable")
        else:
            info.issues.append("invalid_url_format")

    if info.platform == VideoPlatform.SCREEN_STUDIO and "uploading" in lower:
        info.is_valid = False
        info.issues.append("video_still_uploading")

    return info


# ---------------------------------------------------------------------------
# Lateness detection
# ---------------------------------------------------------------------------

def compute_lateness(timestamp_str: str, cfg: ReviewConfig) -> TimingInfo:
    timing = TimingInfo(submitted_utc=timestamp_str.strip())

    if not cfg.hackathon or not cfg.hackathon.deadline_utc:
        return timing

    try:
        ts = datetime.fromisoformat(timestamp_str.strip())
        deadline = datetime.fromisoformat(cfg.hackathon.deadline_utc)
    except (ValueError, TypeError):
        return timing

    if ts > deadline:
        delta_minutes = (ts - deadline).total_seconds() / 60
        timing.is_late = True
        timing.minutes_late = round(delta_minutes, 1)

        grace = cfg.hackathon.grace_period_minutes
        if delta_minutes <= grace:
            timing.lateness_category = LatenessCategory.GRACE_PERIOD
        elif delta_minutes <= 60:
            timing.lateness_category = LatenessCategory.MODERATELY_LATE
        else:
            timing.lateness_category = LatenessCategory.SIGNIFICANTLY_LATE

    return timing


# ---------------------------------------------------------------------------
# CSV column auto-detection
# ---------------------------------------------------------------------------

COLUMN_ALIASES = {
    "team_name": ["team name", "team", "teamname", "team_name"],
    "team_members": ["team members", "members", "team_members", "participants"],
    "project_name": ["project name", "project", "projectname", "project_name", "submission name"],
    "description": ["project description", "description", "desc", "summary", "about"],
    "github_url": ["public github repository", "github", "github url", "github_url", "repo", "repository", "github repo"],
    "video_url": ["demo video", "video", "video url", "video_url", "demo", "demo url"],
    "submitted_at": ["time submitted", "submitted", "submitted_at", "timestamp", "submission time"],
}


def _auto_detect_columns(headers: list[str]) -> dict[str, str | None]:
    """Try to match CSV headers to our expected fields."""
    lower_headers = {h.lower().strip(): h for h in headers}
    mapping: dict[str, str | None] = {}

    for field, aliases in COLUMN_ALIASES.items():
        mapping[field] = None
        for alias in aliases:
            if alias in lower_headers:
                mapping[field] = lower_headers[alias]
                break

    return mapping


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_members(raw: str) -> list[TeamMember]:
    members = []
    for match in re.finditer(r"([^(,]+?)\s*\(([^)]+)\)", raw):
        members.append(TeamMember(name=match.group(1).strip(), email=match.group(2).strip()))
    if not members and raw.strip():
        members.append(TeamMember(name=raw.strip()))
    return members


def _sanitize_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:50]


def parse_csv(cfg: ReviewConfig) -> list[Submission]:
    """Parse the submissions CSV using column mapping from config."""
    if not cfg.csv_path or not cfg.csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {cfg.csv_path}")

    with open(cfg.csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Build effective column mapping
        col = cfg.columns
        auto = _auto_detect_columns(headers)

        def _get(row: dict, field: str, fallback: str | None = None) -> str:
            configured = getattr(col, field, None)
            if configured and configured in row and row[configured]:
                return row[configured].strip()
            if fallback and fallback in row and row[fallback]:
                return row[fallback].strip()
            auto_col = auto.get(field)
            if auto_col and auto_col in row and row[auto_col]:
                return row[auto_col].strip()
            return ""

        submissions: list[Submission] = []

        for idx, row in enumerate(reader, start=1):
            team_name = _get(row, "team_name")
            project_name = _get(row, "project_name") or team_name
            sanitized = f"{idx:03d}_{_sanitize_name(project_name)}"

            members_raw = _get(row, "team_members")
            members = _parse_members(members_raw) if members_raw else []

            github = classify_github_url(_get(row, "github_url"))
            video = classify_video_url(_get(row, "video_url"))

            submitted_at = _get(row, "submitted_at")
            timing = compute_lateness(submitted_at, cfg) if submitted_at else TimingInfo()

            extra: dict[str, str] = {}
            for extra_col in col.extra:
                if extra_col in row:
                    extra[extra_col] = row[extra_col].strip()

            submissions.append(Submission(
                team_number=idx,
                team_name=team_name,
                project_name=project_name,
                sanitized_name=sanitized,
                members=members,
                description=_get(row, "description"),
                github=github,
                video=video,
                timing=timing,
                extra_fields=extra,
            ))

    return submissions


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def run_parse(cfg: ReviewConfig) -> list[Submission]:
    """Parse CSV, print summary, save to JSON."""
    click.echo("\n--- Stage 1: Parse Submissions ---")
    submissions = parse_csv(cfg)

    valid_gh = sum(1 for s in submissions if s.github.is_valid)
    valid_vid = sum(1 for s in submissions if s.video.is_valid)
    late = sum(1 for s in submissions if s.timing.is_late)

    click.echo(f"  Total submissions: {len(submissions)}")
    click.echo(f"  Valid GitHub URLs: {valid_gh}/{len(submissions)}")
    click.echo(f"  Valid video URLs:  {valid_vid}/{len(submissions)}")
    if cfg.hackathon:
        click.echo(f"  Late submissions:  {late}")

    out_path = cfg.data_dir / "submissions.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([s.model_dump(mode="json") for s in submissions], f, indent=2, ensure_ascii=False)
    click.echo(f"  Saved to {out_path}")

    return submissions


def load_submissions(cfg: ReviewConfig) -> list[Submission]:
    """Load previously parsed submissions from JSON."""
    path = cfg.data_dir / "submissions.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the parse stage first.")
    with open(path) as f:
        return [Submission(**s) for s in json.load(f)]

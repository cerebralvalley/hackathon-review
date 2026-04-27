"""Content-addressed cache keys for cloned repos and downloaded videos.

Files in the hackathon-level shared cache used to be keyed by
`sanitized_name`, which encoded the row position from a specific CSV.
That meant a re-uploaded CSV with the same data but a slightly different
row order or project-name spelling would produce different keys and miss
the cache. Hashing the URL instead makes cache hits robust to:

- Row reordering in the CSV
- Project / team name changes
- Two teams sharing the same repo / video (rare but possible)
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hackathon_reviewer.models import Submission


def url_cache_key(url: str) -> str:
    """Stable 16-char hex SHA-256 of a URL (lowercased + stripped)."""
    if not url:
        return ""
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:16]


def repo_cache_key(sub: "Submission") -> str:
    """Cache key for a team's cloned repo. Derived from the clone URL.

    Fallback to a team-number-based unique key when no URL is available
    (avoids two `unknown` teams colliding in the cache dir).
    """
    url = (sub.github.clone_url or sub.github.original or "").strip()
    if not url:
        return f"unknown_{sub.team_number:03d}"
    return url_cache_key(url)


def video_cache_key(sub: "Submission") -> str:
    """Cache key for a team's downloaded video. Derived from the original URL."""
    url = (sub.video.original or "").strip()
    if not url:
        return f"unknown_{sub.team_number:03d}"
    return url_cache_key(url)


def resolve_repo_dir(repos_dir, sub: "Submission"):
    """Return the path where this team's cloned repo lives, migrating from
    the legacy sanitized_name path on the fly if needed.

    The lazy migration in _clone_repo only fires when a clone is actually
    attempted, which skips cache-hit teams during a resume / refresh
    acquisition. Downstream stages (static_analysis, code_review) that
    only READ the repo would otherwise miss those teams entirely.
    """
    new_dir = repos_dir / repo_cache_key(sub)
    if new_dir.exists():
        return new_dir
    legacy = repos_dir / sub.sanitized_name
    if legacy != new_dir and legacy.exists():
        try:
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(new_dir)
            return new_dir
        except OSError:
            return legacy
    return new_dir


def resolve_video_path(videos_dir, sub: "Submission"):
    """Return the path for this team's downloaded video, migrating from the
    legacy sanitized_name path on the fly. Mirrors resolve_repo_dir.
    """
    new_path = videos_dir / f"{video_cache_key(sub)}.mp4"
    if new_path.exists():
        return new_path
    legacy = videos_dir / f"{sub.sanitized_name}.mp4"
    if legacy != new_path and legacy.exists():
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(new_path)
            # Also migrate the _prepared sibling if present
            legacy_prep = videos_dir / f"{sub.sanitized_name}_prepared.mp4"
            new_prep = videos_dir / f"{video_cache_key(sub)}_prepared.mp4"
            if legacy_prep.exists() and not new_prep.exists():
                try:
                    legacy_prep.rename(new_prep)
                except OSError:
                    pass
            return new_path
        except OSError:
            return legacy
    return new_path

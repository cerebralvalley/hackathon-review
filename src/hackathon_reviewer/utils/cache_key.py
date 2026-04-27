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

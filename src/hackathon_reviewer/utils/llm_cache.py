"""Hackathon-level cache for LLM analysis results.

Re-running the pipeline for the same hackathon shouldn't re-pay for an LLM
review when neither the prompt config nor the underlying input has changed.
This module saves each per-team result keyed by:

  (config_signature, input_signature)

Where config_signature is a hash of the relevant ReviewConfig fields and
input_signature captures the actual inputs the LLM saw (repo HEAD SHA for
code review, video file size+mtime for video analysis). On lookup, both
must match — so a config edit OR a re-clone/re-download invalidates the
cache for that team automatically.

CLI mode leaves cfg.cache_dir as None and the helpers no-op.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def stable_hash(payload: Any) -> str:
    """Short stable SHA256 of a JSON-serializable payload."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def repo_head_sha(repo_dir: Path) -> str | None:
    """Return the current git HEAD SHA for the cloned repo, or None."""
    from hackathon_reviewer.utils.git import run_git
    try:
        rc, stdout, _ = run_git(["rev-parse", "HEAD"], str(repo_dir))
        if rc == 0:
            return stdout.strip() or None
    except Exception:
        pass
    return None


def video_file_signature(video_path: Path | str | None) -> str | None:
    """Cheap input signature for a video: size + mtime (1s resolution)."""
    if not video_path:
        return None
    p = Path(video_path)
    if not p.exists():
        return None
    try:
        st = p.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return None


class LLMCache:
    """Per-team JSON cache under <cache_root>/<namespace>/<team_number>.json.

    Each cache file stores the result plus the config and input signatures
    used when it was generated. `load` returns the result only if both
    signatures match the current ones.
    """

    def __init__(self, cache_root: Path | None, namespace: str):
        self.namespace = namespace
        self.dir: Path | None = (cache_root / namespace) if cache_root else None

    @property
    def enabled(self) -> bool:
        return self.dir is not None

    def _path(self, team_number: int) -> Path | None:
        if not self.dir:
            return None
        return self.dir / f"{team_number:04d}.json"

    def load(
        self,
        team_number: int,
        config_sig: str,
        input_sig: str | None,
    ) -> dict | None:
        path = self._path(team_number)
        if not path or not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("config_sig") != config_sig:
            return None
        if payload.get("input_sig") != input_sig:
            return None
        return payload.get("result")

    def save(
        self,
        team_number: int,
        config_sig: str,
        input_sig: str | None,
        result: dict,
    ) -> None:
        path = self._path(team_number)
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "team_number": team_number,
            "config_sig": config_sig,
            "input_sig": input_sig,
            "result": result,
            "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

"""Stage 3: Download demo videos."""

from __future__ import annotations

import json
from pathlib import Path

import click
from tqdm import tqdm

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    Submission,
    VideoDownloadResult,
    VideoPlatform,
)
from hackathon_reviewer.utils.video_download import (
    download_gdown,
    download_ytdlp,
    get_video_duration,
)


def _download_one(sub: Submission, cfg: ReviewConfig) -> VideoDownloadResult:
    result = VideoDownloadResult()
    video = sub.video

    if not video.is_valid:
        result.error = f"invalid_video_url: {', '.join(video.issues)}"
        return result

    video_path = cfg.videos_dir / f"{sub.sanitized_name}.mp4"

    # Already downloaded
    if video_path.exists() and video_path.stat().st_size > 0:
        result.success = True
        result.method = "cached"
        result.file_path = str(video_path)
        result.duration_seconds = round(get_video_duration(video_path), 1)
        return result

    video_path.parent.mkdir(parents=True, exist_ok=True)
    url = video.original

    if video.platform == VideoPlatform.GOOGLE_DRIVE:
        success, error = download_gdown(url, video_path)
        if not success:
            success, error = download_ytdlp(url, video_path)
        result.method = "gdown+yt-dlp"
    else:
        success, error = download_ytdlp(url, video_path)
        result.method = "yt-dlp"

    result.success = success
    result.error = error

    if success and video_path.exists():
        result.file_path = str(video_path)
        result.duration_seconds = round(get_video_duration(video_path), 1)

    return result


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def run_video_download(
    cfg: ReviewConfig,
    submissions: list[Submission],
    resume: bool = True,
) -> dict[int, VideoDownloadResult]:
    """Download all demo videos, save results to JSON."""
    click.echo("\n--- Stage 3: Download Videos ---")

    existing: dict[int, VideoDownloadResult] = {}
    out_path = cfg.data_dir / "video_downloads.json"
    if resume and out_path.exists():
        existing = _load_downloads_file(out_path)
        click.echo(f"  Resuming: {len(existing)} already processed")

    results: dict[int, VideoDownloadResult] = {}
    for sub in tqdm(submissions, desc="Downloading videos"):
        if resume and sub.team_number in existing and existing[sub.team_number].success:
            results[sub.team_number] = existing[sub.team_number]
        else:
            results[sub.team_number] = _download_one(sub, cfg)

    downloaded = sum(1 for r in results.values() if r.success)
    click.echo(f"  Downloaded: {downloaded}/{len(results)}")

    serializable = {str(k): v.model_dump(mode="json") for k, v in results.items()}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    click.echo(f"  Saved to {out_path}")

    return results


def _load_downloads_file(path: Path) -> dict[int, VideoDownloadResult]:
    with open(path) as f:
        raw = json.load(f)
    return {int(k): VideoDownloadResult(**v) for k, v in raw.items()}


def load_video_downloads(cfg: ReviewConfig) -> dict[int, VideoDownloadResult]:
    """Load previously saved video download results."""
    path = cfg.data_dir / "video_downloads.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the video download stage first.")
    return _load_downloads_file(path)

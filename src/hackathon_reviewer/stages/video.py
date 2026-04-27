"""Stage 3: Download demo videos (parallelized)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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


MAX_DOWNLOAD_RETRIES = 2
RETRY_DELAY = 3


def _download_one(
    sub: Submission, cfg: ReviewConfig
) -> tuple[int, VideoDownloadResult]:
    """Download a single video with auto-retry. Returns (team_number, result)."""
    import time
    from hackathon_reviewer.utils.cache_key import video_cache_key

    result = VideoDownloadResult()
    video = sub.video

    if not video.is_valid:
        result.error = f"invalid_video_url: {', '.join(video.issues)}"
        return sub.team_number, result

    cache_key = video_cache_key(sub)
    video_path = cfg.videos_dir / f"{cache_key}.mp4"
    legacy_path = cfg.videos_dir / f"{sub.sanitized_name}.mp4"

    if video_path.exists() and video_path.stat().st_size > 0:
        result.success = True
        result.method = "cached"
        result.file_path = str(video_path)
        result.duration_seconds = round(get_video_duration(video_path), 1)
        return sub.team_number, result

    # One-time migration from sanitized_name path to URL-hash path
    if (
        legacy_path != video_path
        and legacy_path.exists()
        and legacy_path.stat().st_size > 0
    ):
        try:
            legacy_path.rename(video_path)
            legacy_prepared = cfg.videos_dir / f"{sub.sanitized_name}_prepared.mp4"
            new_prepared = cfg.videos_dir / f"{cache_key}_prepared.mp4"
            if legacy_prepared.exists() and not new_prepared.exists():
                try:
                    legacy_prepared.rename(new_prepared)
                except OSError:
                    pass
            result.success = True
            result.method = "cached"
            result.file_path = str(video_path)
            result.duration_seconds = round(get_video_duration(video_path), 1)
            return sub.team_number, result
        except OSError:
            pass  # fall through to fresh download

    video_path.parent.mkdir(parents=True, exist_ok=True)
    url = video.original

    last_error = None
    for attempt in range(1 + MAX_DOWNLOAD_RETRIES):
        if attempt > 0:
            video_path.unlink(missing_ok=True)
            time.sleep(RETRY_DELAY * attempt)

        if video.platform == VideoPlatform.GOOGLE_DRIVE:
            success, error = download_gdown(url, video_path)
            if not success:
                success, error = download_ytdlp(url, video_path)
            result.method = "gdown+yt-dlp"
        else:
            success, error = download_ytdlp(url, video_path)
            result.method = "yt-dlp"

        if success:
            result.success = True
            result.error = None
            if video_path.exists():
                result.file_path = str(video_path)
                result.duration_seconds = round(get_video_duration(video_path), 1)
            return sub.team_number, result

        last_error = error

    result.success = False
    result.error = last_error
    return sub.team_number, result


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------


def run_video_download(
    cfg: ReviewConfig,
    submissions: list[Submission],
    resume: bool = True,
    progress: "Any | None" = None,
) -> dict[int, VideoDownloadResult]:
    """Download all demo videos in parallel, save results to JSON."""
    click.echo("\n--- Stage 3: Download Videos ---")
    workers = cfg.concurrency.video_download_workers
    click.echo(f"  Workers: {workers}")

    existing: dict[int, VideoDownloadResult] = {}
    out_path = cfg.data_dir / "video_downloads.json"
    if resume and out_path.exists():
        existing = _load_downloads_file(out_path)
        click.echo(f"  Resuming: {len(existing)} already processed")

    sub_by_team = {s.team_number: s for s in submissions}
    results: dict[int, VideoDownloadResult] = {}
    work: list[Submission] = []

    for sub in submissions:
        if resume and sub.team_number in existing and existing[sub.team_number].success:
            results[sub.team_number] = existing[sub.team_number]
        else:
            work.append(sub)

    total = len(submissions)
    done = total - len(work)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_download_one, sub, cfg): sub.team_number for sub in work
        }
        for future in tqdm(
            as_completed(futures), total=len(futures), desc="Downloading videos"
        ):
            team_num, result = future.result()
            results[team_num] = result
            done += 1
            if not result.success and progress:
                sub = sub_by_team[team_num]
                progress.add_failure(team_num, sub.team_name, sub.project_name, result.error or "unknown")
            if progress:
                progress.update(done, total, "")

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
        raise FileNotFoundError(
            f"{path} not found. Run the video download stage first."
        )
    return _load_downloads_file(path)

"""Video download helpers using yt-dlp and gdown."""

from __future__ import annotations

import subprocess
from pathlib import Path

DOWNLOAD_TIMEOUT = 300


def download_ytdlp(url: str, output_path: Path) -> tuple[bool, str | None]:
    """Download a video using yt-dlp. Returns (success, error)."""
    try:
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--max-filesize", "500M",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            "--socket-timeout", "30",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT)
        if proc.returncode == 0 and output_path.exists():
            return True, None
        return False, (proc.stderr.strip()[:300] if proc.stderr else "download_failed")
    except subprocess.TimeoutExpired:
        return False, "download_timeout"
    except FileNotFoundError:
        return False, "yt-dlp_not_installed"
    except Exception as e:
        return False, str(e)[:200]


def download_gdown(url: str, output_path: Path) -> tuple[bool, str | None]:
    """Download a Google Drive video using gdown. Returns (success, error)."""
    try:
        import gdown

        file_id = None
        if "/file/d/" in url:
            file_id = url.split("/file/d/")[1].split("/")[0]
        elif "id=" in url:
            file_id = url.split("id=")[1].split("&")[0]
        elif "/d/" in url:
            file_id = url.split("/d/")[1].split("/")[0]

        if not file_id:
            return False, "could_not_extract_drive_file_id"

        download_url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(download_url, str(output_path), quiet=True, fuzzy=True)

        if output_path.exists():
            return True, None
        return False, "gdown_download_failed"
    except Exception as e:
        return False, str(e)[:200]


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def prepare_video_for_upload(video_path: Path, max_duration: int = 300) -> Path:
    """Trim to max_duration and downscale to 720p for faster Gemini upload.

    Returns the path to the prepared file (may be original if no processing needed,
    or a new _prepared.mp4 file).
    """
    prepared_path = video_path.with_name(video_path.stem + "_prepared.mp4")
    if prepared_path.exists() and prepared_path.stat().st_size > 0:
        return prepared_path

    duration = get_video_duration(video_path)
    needs_trim = duration > max_duration
    needs_scale = _video_height(video_path) > 720

    if not needs_trim and not needs_scale:
        return video_path

    try:
        cmd = ["ffmpeg", "-i", str(video_path)]
        if needs_trim:
            cmd += ["-t", str(max_duration)]
        if needs_scale:
            cmd += ["-vf", "scale=-2:720"]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-y", str(prepared_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0 and prepared_path.exists():
            return prepared_path
    except Exception:
        pass

    return video_path


def _video_height(video_path: Path) -> int:
    """Get video height in pixels using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=height",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except Exception:
        pass
    return 0

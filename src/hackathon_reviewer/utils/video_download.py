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

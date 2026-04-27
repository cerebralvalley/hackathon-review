"""File path management for hackathon runs."""

from __future__ import annotations

from pathlib import Path

from api.app.config import settings


def hackathon_dir(hackathon_id: str) -> Path:
    return settings.data_root / hackathon_id


def csv_path(hackathon_id: str, filename: str) -> Path:
    return hackathon_dir(hackathon_id) / filename


def run_output_dir(hackathon_id: str, run_id: str) -> Path:
    return hackathon_dir(hackathon_id) / "runs" / run_id


def ensure_hackathon_dir(hackathon_id: str) -> Path:
    d = hackathon_dir(hackathon_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_run_dir(hackathon_id: str, run_id: str) -> Path:
    d = run_output_dir(hackathon_id, run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_data_dir(hackathon_id: str, run_id: str) -> Path:
    return run_output_dir(hackathon_id, run_id) / "data"


def run_reports_dir(hackathon_id: str, run_id: str) -> Path:
    return run_output_dir(hackathon_id, run_id) / "reports"


def run_videos_dir(hackathon_id: str, run_id: str) -> Path:
    return run_output_dir(hackathon_id, run_id) / "videos"


def run_logs_dir(hackathon_id: str, run_id: str) -> Path:
    return run_output_dir(hackathon_id, run_id) / "logs"

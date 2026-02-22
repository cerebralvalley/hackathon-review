"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class ColumnMapping(BaseModel):
    team_name: str = "Team Name"
    team_members: str | None = "Team Members"
    project_name: str | None = "Project Name"
    description: str | None = "Project Description"
    github_url: str = "Public GitHub Repository"
    video_url: str = "Demo Video"
    submitted_at: str | None = None
    extra: list[str] = Field(default_factory=list)


class CodeReviewConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    max_tokens: int = 2000
    max_source_chars: int = 20000


class VideoAnalysisConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-3-flash-preview"
    max_video_duration: int = 180


class HackathonConfig(BaseModel):
    """Optional hackathon-specific settings."""
    name: str = ""
    deadline_utc: str | None = None
    grace_period_minutes: int = 15
    start_date: str | None = None
    end_date: str | None = None
    verify_git_period: bool = False


class ScoringCriterion(BaseModel):
    weight: float
    description: str = ""


class ScoringConfig(BaseModel):
    criteria: dict[str, ScoringCriterion] = Field(default_factory=dict)


class ConcurrencyConfig(BaseModel):
    clone_workers: int = 4
    video_download_workers: int = 4
    llm_concurrent_requests: int = 3


class ReviewConfig(BaseModel):
    """Top-level configuration for the pipeline."""
    columns: ColumnMapping = Field(default_factory=ColumnMapping)
    code_review: CodeReviewConfig = Field(default_factory=CodeReviewConfig)
    video_analysis: VideoAnalysisConfig = Field(default_factory=VideoAnalysisConfig)
    hackathon: HackathonConfig | None = None
    scoring: ScoringConfig | None = None
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)

    # Runtime paths (set by CLI, not from YAML)
    csv_path: Path | None = None
    output_dir: Path = Path("./output")

    @property
    def data_dir(self) -> Path:
        return self.output_dir / "data"

    @property
    def repos_dir(self) -> Path:
        return self.output_dir / "repos"

    @property
    def videos_dir(self) -> Path:
        return self.output_dir / "videos"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def anthropic_api_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def gemini_api_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY", "")

    def ensure_dirs(self) -> None:
        """Create all output directories and resolve to absolute paths."""
        self.output_dir = self.output_dir.resolve()
        for d in [self.data_dir, self.repos_dir, self.videos_dir,
                  self.reports_dir, self.reports_dir / "projects"]:
            d.mkdir(parents=True, exist_ok=True)


def load_config(config_path: str | Path | None = None) -> ReviewConfig:
    """Load config from a YAML file, falling back to defaults."""
    if config_path is None:
        return ReviewConfig()

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return ReviewConfig(**raw)

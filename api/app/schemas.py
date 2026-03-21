"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Hackathon
# ---------------------------------------------------------------------------

class HackathonCreate(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class HackathonUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


class HackathonResponse(BaseModel):
    id: str
    name: str
    config: dict[str, Any]
    csv_filename: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HackathonListResponse(BaseModel):
    id: str
    name: str
    csv_filename: str | None
    created_at: datetime
    latest_run_status: str | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pipeline Run
# ---------------------------------------------------------------------------

class RunCreate(BaseModel):
    resume: bool = True


class RunResponse(BaseModel):
    id: str
    hackathon_id: str
    status: str
    current_stage: str | None
    stage_progress: dict[str, Any]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class LeaderboardEntry(BaseModel):
    rank: int
    team_number: int
    team_name: str
    project_name: str
    weighted_total: float
    scores: dict[str, float]
    total_loc: int = 0
    primary_language: str = "unknown"
    commits: int = 0
    integration_depth: str = "none"
    github_url: str = ""
    video_url: str = ""


class ProjectSummary(BaseModel):
    team_number: int
    team_name: str
    project_name: str
    weighted_total: float = 0.0
    flags_count: int = 0


class FlagResponse(BaseModel):
    team_number: int
    team_name: str
    project_name: str
    flag_type: str
    description: str
    severity: str

"""Pydantic data models for all pipeline stages."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VideoPlatform(str, Enum):
    YOUTUBE = "youtube"
    LOOM = "loom"
    VIMEO = "vimeo"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    DESCRIPT = "descript"
    SCREEN_STUDIO = "screen_studio"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class HackathonPeriodFlag(str, Enum):
    CLEAN = "clean"
    MINOR_PRIOR_WORK = "minor_prior_work"
    SIGNIFICANT_PRIOR_WORK = "significant_prior_work"
    PRE_EXISTING_PROJECT = "pre_existing_project"
    UNKNOWN = "unknown"


class IntegrationDepth(str, Enum):
    NONE = "none"
    BASIC = "basic"
    MODERATE = "moderate"
    DEEP = "deep"
    EXTENSIVE = "extensive"


class DemoClassification(str, Enum):
    BROKEN = "broken"
    SLIDES_ONLY = "slides_only"
    BASIC_WORKING = "basic_working"
    POLISHED = "polished"
    EXCEPTIONAL = "exceptional"
    UNKNOWN = "unknown"


class LatenessCategory(str, Enum):
    ON_TIME = "on_time"
    GRACE_PERIOD = "grace_period"
    MODERATELY_LATE = "moderately_late"
    SIGNIFICANTLY_LATE = "significantly_late"


# ---------------------------------------------------------------------------
# Submission (parsed from CSV)
# ---------------------------------------------------------------------------

class GitHubInfo(BaseModel):
    original: str = ""
    cleaned: str | None = None
    clone_url: str | None = None
    is_valid: bool = False
    issues: list[str] = Field(default_factory=list)


class VideoInfo(BaseModel):
    original: str = ""
    platform: VideoPlatform = VideoPlatform.UNKNOWN
    is_valid: bool = False
    issues: list[str] = Field(default_factory=list)


class TeamMember(BaseModel):
    name: str
    email: str = ""


class TimingInfo(BaseModel):
    submitted_utc: str = ""
    is_late: bool = False
    minutes_late: float = 0.0
    lateness_category: LatenessCategory = LatenessCategory.ON_TIME


class Submission(BaseModel):
    """A single parsed submission from the CSV."""
    team_number: int
    team_name: str
    project_name: str
    sanitized_name: str
    members: list[TeamMember] = Field(default_factory=list)
    description: str = ""
    github: GitHubInfo = Field(default_factory=GitHubInfo)
    video: VideoInfo = Field(default_factory=VideoInfo)
    timing: TimingInfo = Field(default_factory=TimingInfo)
    extra_fields: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repo metadata (from cloning + git analysis)
# ---------------------------------------------------------------------------

class GitHistory(BaseModel):
    first_commit_date: str | None = None
    last_commit_date: str | None = None
    total_commits: int = 0
    commits_before_hackathon: int = 0
    commits_during_hackathon: int = 0
    commits_after_deadline: int = 0
    hackathon_period_flag: HackathonPeriodFlag = HackathonPeriodFlag.UNKNOWN
    is_fork: bool = False
    is_single_commit_dump: bool = False
    commit_authors: list[str] = Field(default_factory=list)


class RepoFiles(BaseModel):
    file_count: int = 0
    total_loc: int = 0
    primary_language: str = "unknown"
    languages: dict[str, int] = Field(default_factory=dict)
    has_readme: bool = False
    has_tests: bool = False


class RepoMetadata(BaseModel):
    """Result of cloning and analyzing a repository."""
    team_number: int
    team_name: str
    project_name: str
    sanitized_name: str
    clone_success: bool = False
    clone_error: str | None = None
    files: RepoFiles = Field(default_factory=RepoFiles)
    git_history: GitHistory = Field(default_factory=GitHistory)


# ---------------------------------------------------------------------------
# Static analysis
# ---------------------------------------------------------------------------

class PatternMatch(BaseModel):
    description: str
    files: list[str] = Field(default_factory=list)
    match_count: int = 0


class RepoStructure(BaseModel):
    top_level_dirs: list[str] = Field(default_factory=list)
    top_level_files: list[str] = Field(default_factory=list)
    has_docker: bool = False
    has_ci: bool = False
    has_env_example: bool = False
    has_claude_md: bool = False
    has_license: bool = False
    frameworks_detected: list[str] = Field(default_factory=list)


class StaticAnalysisResult(BaseModel):
    """Result of static code analysis (no LLM)."""
    team_number: int
    clone_success: bool = False
    integration_patterns: dict[str, PatternMatch] = Field(default_factory=dict)
    integration_score: int = 0
    integration_depth: IntegrationDepth = IntegrationDepth.NONE
    boilerplate_type: str | None = None
    is_boilerplate_heavy: bool = False
    structure: RepoStructure = Field(default_factory=RepoStructure)


# ---------------------------------------------------------------------------
# LLM code review
# ---------------------------------------------------------------------------

class CriterionScore(BaseModel):
    score: float
    rationale: str = ""
    source: str = "automated"


class CodeReviewResult(BaseModel):
    """Result of LLM-powered code review."""
    team_number: int
    success: bool = False
    error: str | None = None
    review_text: str = ""
    scores: dict[str, CriterionScore] = Field(default_factory=dict)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Video analysis
# ---------------------------------------------------------------------------

class VideoDownloadResult(BaseModel):
    success: bool = False
    error: str | None = None
    method: str = ""
    file_path: str | None = None
    duration_seconds: float = 0.0


class VideoAnalysisResult(BaseModel):
    """Result of Gemini video understanding."""
    team_number: int
    download: VideoDownloadResult = Field(default_factory=VideoDownloadResult)
    analysis_success: bool = False
    analysis_error: str | None = None
    transcript_summary: str = ""
    demo_classification: DemoClassification = DemoClassification.UNKNOWN
    is_related_to_project: bool = True
    review_text: str = ""
    scores: dict[str, CriterionScore] = Field(default_factory=dict)
    model_used: str = ""


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class ProjectScore(BaseModel):
    """Final combined score for a submission."""
    team_number: int
    team_name: str
    project_name: str
    scores: dict[str, CriterionScore] = Field(default_factory=dict)
    weighted_total: float = 0.0
    score_source: str = "automated"


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

class ProjectFlag(BaseModel):
    team_number: int
    team_name: str
    project_name: str
    flag_type: str
    description: str
    severity: str = "warning"


class ProjectReport(BaseModel):
    """Combined report for a single project."""
    submission: Submission
    repo_metadata: RepoMetadata | None = None
    static_analysis: StaticAnalysisResult | None = None
    code_review: CodeReviewResult | None = None
    video_analysis: VideoAnalysisResult | None = None
    score: ProjectScore | None = None
    flags: list[ProjectFlag] = Field(default_factory=list)

"""Abstract base for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CodeReviewContext:
    """Everything an LLM needs to review a project's code."""
    project_name: str
    team_name: str
    team_number: int
    description: str
    source_files: str  # formatted key source file contents
    loc: int = 0
    commits: int = 0
    primary_language: str = "unknown"
    has_tests: bool = False
    has_claude_md: bool = False
    period_flag: str = "unknown"
    is_single_dump: bool = False
    integration_patterns: str = ""
    transcript: str = ""
    extra_context: dict[str, str] = field(default_factory=dict)


@dataclass
class CodeReviewResponse:
    success: bool = False
    error: str | None = None
    review_text: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class VideoReviewContext:
    """Everything needed for video analysis."""
    project_name: str
    team_name: str
    team_number: int
    description: str
    video_path: Path | None = None
    max_duration: int = 180


@dataclass
class VideoReviewResponse:
    success: bool = False
    error: str | None = None
    transcript_summary: str = ""
    demo_classification: str = "unknown"
    is_related_to_project: bool = True
    review_text: str = ""
    scores: dict[str, float] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def review_code(self, context: CodeReviewContext) -> CodeReviewResponse:
        ...

    def review_video(self, context: VideoReviewContext) -> VideoReviewResponse:
        raise NotImplementedError(f"{self.__class__.__name__} does not support video review")

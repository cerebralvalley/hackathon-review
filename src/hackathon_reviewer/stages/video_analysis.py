"""Stage 6: Video analysis via Gemini native video understanding."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
from tqdm import tqdm

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    CriterionScore,
    DemoClassification,
    Submission,
    VideoAnalysisResult,
    VideoDownloadResult,
)
from hackathon_reviewer.providers.base import VideoReviewContext


DEMO_CLASSIFICATION_MAP = {
    "broken": DemoClassification.BROKEN,
    "slides_only": DemoClassification.SLIDES_ONLY,
    "basic_working": DemoClassification.BASIC_WORKING,
    "polished": DemoClassification.POLISHED,
    "exceptional": DemoClassification.EXCEPTIONAL,
}


def _build_provider(cfg: ReviewConfig):
    provider_name = cfg.video_analysis.provider.lower()
    if provider_name == "gemini":
        from hackathon_reviewer.providers.gemini import GeminiProvider
        if not cfg.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set. Required for video analysis.")
        return GeminiProvider(
            api_key=cfg.gemini_api_key,
            model=cfg.video_analysis.model,
        )
    else:
        raise ValueError(f"Unknown video analysis provider: {provider_name}. Only 'gemini' supports native video.")


def _analyze_one(
    provider,
    sub: Submission,
    download: VideoDownloadResult,
    cfg: ReviewConfig,
) -> VideoAnalysisResult:
    result = VideoAnalysisResult(
        team_number=sub.team_number,
        download=download,
        model_used=cfg.video_analysis.model,
    )

    if not download.success or not download.file_path:
        result.analysis_error = "video_not_available"
        return result

    video_path = Path(download.file_path)
    if not video_path.exists():
        result.analysis_error = "video_file_missing"
        return result

    ctx = VideoReviewContext(
        project_name=sub.project_name,
        team_name=sub.team_name,
        team_number=sub.team_number,
        description=sub.description,
        video_path=video_path,
        max_duration=cfg.video_analysis.max_video_duration,
    )

    resp = provider.review_video(ctx)

    result.analysis_success = resp.success
    result.analysis_error = resp.error
    result.transcript_summary = resp.transcript_summary
    result.is_related_to_project = resp.is_related_to_project
    result.review_text = resp.review_text

    classification = resp.demo_classification.lower()
    result.demo_classification = DEMO_CLASSIFICATION_MAP.get(
        classification, DemoClassification.UNKNOWN
    )

    for key, val in resp.scores.items():
        result.scores[key] = CriterionScore(score=val, source=cfg.video_analysis.provider)

    return result


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def run_video_analysis(
    cfg: ReviewConfig,
    submissions: list[Submission],
    video_downloads: dict[int, VideoDownloadResult],
    resume: bool = True,
) -> list[VideoAnalysisResult]:
    """Run Gemini video analysis on all downloaded videos, save to JSON."""
    click.echo("\n--- Stage 6: Video Analysis ---")
    click.echo(f"  Provider: {cfg.video_analysis.provider} ({cfg.video_analysis.model})")

    provider = _build_provider(cfg)

    existing: dict[int, VideoAnalysisResult] = {}
    out_path = cfg.data_dir / "video_analysis.json"
    if resume and out_path.exists():
        existing = {r.team_number: r for r in _load_analysis_file(out_path)}
        click.echo(f"  Resuming: {len(existing)} already analyzed")

    results: list[VideoAnalysisResult] = []
    start = time.time()

    for i, sub in enumerate(tqdm(submissions, desc="Video analysis")):
        if resume and sub.team_number in existing and existing[sub.team_number].analysis_success:
            results.append(existing[sub.team_number])
            continue

        download = video_downloads.get(sub.team_number, VideoDownloadResult())
        result = _analyze_one(provider, sub, download, cfg)
        results.append(result)

        # Save progress every 25
        if (i + 1) % 25 == 0:
            _save_analysis(results, out_path)

    _save_analysis(results, out_path)

    elapsed = time.time() - start
    analyzed = sum(1 for r in results if r.analysis_success)
    unrelated = sum(1 for r in results if r.analysis_success and not r.is_related_to_project)
    click.echo(f"  Analyzed: {analyzed}/{len(results)}")
    if unrelated:
        click.echo(f"  Flagged as unrelated: {unrelated}")
    click.echo(f"  Time: {elapsed:.0f}s")
    click.echo(f"  Saved to {out_path}")

    return results


def _save_analysis(results: list[VideoAnalysisResult], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump(mode="json") for r in results], f, indent=2, ensure_ascii=False)


def _load_analysis_file(path: Path) -> list[VideoAnalysisResult]:
    with open(path) as f:
        return [VideoAnalysisResult(**r) for r in json.load(f)]


def load_video_analysis(cfg: ReviewConfig) -> list[VideoAnalysisResult]:
    """Load previously saved video analysis results."""
    path = cfg.data_dir / "video_analysis.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the analyze stage first.")
    return _load_analysis_file(path)

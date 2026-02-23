"""Stage 6: Video analysis via Gemini native video understanding (parallelized)."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from hackathon_reviewer.utils.video_download import prepare_video_for_upload


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

    # Trim long videos and downscale to 720p for faster upload
    prepared_path = prepare_video_for_upload(
        video_path, max_duration=cfg.video_analysis.max_video_duration,
    )

    ctx = VideoReviewContext(
        project_name=sub.project_name,
        team_name=sub.team_name,
        team_number=sub.team_number,
        description=sub.description,
        video_path=prepared_path,
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

_save_lock = threading.Lock()


def run_video_analysis(
    cfg: ReviewConfig,
    submissions: list[Submission],
    video_downloads: dict[int, VideoDownloadResult],
    resume: bool = True,
) -> list[VideoAnalysisResult]:
    """Run Gemini video analysis on all downloaded videos in parallel."""
    click.echo("\n--- Stage 6: Video Analysis ---")
    workers = cfg.concurrency.llm_concurrent_requests
    click.echo(f"  Provider: {cfg.video_analysis.provider} ({cfg.video_analysis.model})")
    click.echo(f"  Workers: {workers}")
    click.echo(f"  Videos >5min will be trimmed and downscaled to 720p")

    provider = _build_provider(cfg)

    existing: dict[int, VideoAnalysisResult] = {}
    out_path = cfg.data_dir / "video_analysis.json"
    if resume and out_path.exists():
        existing = {r.team_number: r for r in _load_analysis_file(out_path)}
        click.echo(f"  Resuming: {len(existing)} already analyzed")

    results_map: dict[int, VideoAnalysisResult] = {}
    work: list[Submission] = []

    for sub in submissions:
        if resume and sub.team_number in existing and existing[sub.team_number].analysis_success:
            results_map[sub.team_number] = existing[sub.team_number]
        else:
            work.append(sub)

    start = time.time()
    completed = 0

    def _do_one(sub: Submission) -> tuple[int, VideoAnalysisResult]:
        download = video_downloads.get(sub.team_number, VideoDownloadResult())
        return sub.team_number, _analyze_one(provider, sub, download, cfg)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_do_one, sub): sub.team_number for sub in work}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Video analysis"):
            team_num, result = future.result()
            results_map[team_num] = result
            completed += 1
            if completed % 10 == 0:
                with _save_lock:
                    _save_analysis_map(results_map, submissions, out_path)

    # Preserve submission order in output
    results = [results_map.get(sub.team_number, VideoAnalysisResult(team_number=sub.team_number))
               for sub in submissions]

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


def _save_analysis_map(results_map: dict[int, VideoAnalysisResult], submissions: list[Submission], path: Path) -> None:
    ordered = [results_map[s.team_number] for s in submissions if s.team_number in results_map]
    _save_analysis(ordered, path)


def _load_analysis_file(path: Path) -> list[VideoAnalysisResult]:
    with open(path) as f:
        return [VideoAnalysisResult(**r) for r in json.load(f)]


def load_video_analysis(cfg: ReviewConfig) -> list[VideoAnalysisResult]:
    """Load previously saved video analysis results."""
    path = cfg.data_dir / "video_analysis.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the analyze stage first.")
    return _load_analysis_file(path)

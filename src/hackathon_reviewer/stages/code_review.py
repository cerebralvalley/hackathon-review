"""Stage 5: LLM-powered code review via pluggable provider (parallelized)."""

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
    CodeReviewResult,
    CriterionScore,
    RepoMetadata,
    StaticAnalysisResult,
    Submission,
)
from hackathon_reviewer.providers.base import CodeReviewContext, LLMProvider, ScoringCriterionDef
from hackathon_reviewer.utils.file_reader import read_key_files


def _get_transcript(cfg: ReviewConfig, sanitized_name: str) -> str:
    """Read video transcript if available."""
    tp = cfg.videos_dir / f"{sanitized_name}_transcript.txt"
    if tp.exists():
        text = tp.read_text(encoding="utf-8").strip()
        return text[:2000] + "... (truncated)" if len(text) > 2000 else text
    return "(no transcript available)"


def _build_provider(cfg: ReviewConfig) -> LLMProvider:
    """Instantiate the configured code review provider."""
    provider_name = cfg.code_review.provider.lower()

    if provider_name == "anthropic":
        from hackathon_reviewer.providers.anthropic import AnthropicProvider
        if not cfg.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Required for Anthropic code review.")
        return AnthropicProvider(
            api_key=cfg.anthropic_api_key,
            model=cfg.code_review.model,
            max_tokens=cfg.code_review.max_tokens,
        )
    elif provider_name == "gemini":
        from hackathon_reviewer.providers.gemini import GeminiProvider
        if not cfg.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set. Required for Gemini code review.")
        return GeminiProvider(
            api_key=cfg.gemini_api_key,
            model=cfg.code_review.model,
        )
    else:
        raise ValueError(f"Unknown code review provider: {provider_name}")


def _review_one(
    provider: LLMProvider,
    sub: Submission,
    meta: RepoMetadata,
    static: StaticAnalysisResult,
    cfg: ReviewConfig,
) -> CodeReviewResult:
    result = CodeReviewResult(
        team_number=sub.team_number,
        model_used=cfg.code_review.model,
    )

    if not meta.clone_success:
        result.error = "repo_not_cloned"
        return result

    repo_dir = cfg.repos_dir / sub.sanitized_name
    source_files = read_key_files(repo_dir, max_chars=cfg.code_review.max_source_chars)
    transcript = _get_transcript(cfg, sub.sanitized_name)

    patterns_str = ", ".join(
        f"{k} ({v.match_count} matches)"
        for k, v in static.integration_patterns.items()
    ) or "none detected"

    criteria_defs = []
    if cfg.scoring and cfg.scoring.criteria:
        for key, crit in cfg.scoring.criteria.items():
            criteria_defs.append(ScoringCriterionDef(
                key=key, weight=crit.weight, description=crit.description,
            ))

    ctx = CodeReviewContext(
        project_name=sub.project_name,
        team_name=sub.team_name,
        team_number=sub.team_number,
        description=sub.description,
        source_files=source_files,
        loc=meta.files.total_loc,
        commits=meta.git_history.commits_during_hackathon or meta.git_history.total_commits,
        primary_language=meta.files.primary_language,
        has_tests=meta.files.has_tests,
        has_claude_md=static.structure.has_claude_md,
        period_flag=meta.git_history.hackathon_period_flag.value,
        is_single_dump=meta.git_history.is_single_commit_dump,
        integration_patterns=patterns_str,
        transcript=transcript,
        extra_context=sub.extra_fields,
        scoring_criteria=criteria_defs,
    )

    resp = provider.review_code(ctx)

    result.success = resp.success
    result.error = resp.error
    result.review_text = resp.review_text
    result.input_tokens = resp.input_tokens
    result.output_tokens = resp.output_tokens

    for key, val in resp.scores.items():
        result.scores[key] = CriterionScore(score=val, source=cfg.code_review.provider)

    return result


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

_save_lock = threading.Lock()


def run_code_review(
    cfg: ReviewConfig,
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    static_results: list[StaticAnalysisResult],
    resume: bool = True,
) -> list[CodeReviewResult]:
    """Run LLM code review on all submissions in parallel, save to JSON."""
    workers = cfg.concurrency.llm_concurrent_requests
    click.echo("\n--- Stage 5: LLM Code Review ---")
    click.echo(f"  Provider: {cfg.code_review.provider} ({cfg.code_review.model})")
    click.echo(f"  Workers: {workers}")

    provider = _build_provider(cfg)

    meta_by_team = {m.team_number: m for m in repo_metadata}
    static_by_team = {s.team_number: s for s in static_results}

    existing: dict[int, CodeReviewResult] = {}
    out_path = cfg.data_dir / "code_reviews.json"
    if resume and out_path.exists():
        existing = {r.team_number: r for r in _load_reviews_file(out_path)}
        click.echo(f"  Resuming: {len(existing)} already reviewed")

    results_map: dict[int, CodeReviewResult] = {}
    work: list[Submission] = []

    for sub in submissions:
        if resume and sub.team_number in existing and existing[sub.team_number].success:
            results_map[sub.team_number] = existing[sub.team_number]
        else:
            meta = meta_by_team.get(sub.team_number)
            static = static_by_team.get(sub.team_number)
            if not meta or not static:
                results_map[sub.team_number] = CodeReviewResult(
                    team_number=sub.team_number, error="missing_data",
                )
            else:
                work.append(sub)

    total_input_tokens = 0
    total_output_tokens = 0
    start = time.time()
    completed = 0

    def _do_one(sub: Submission) -> tuple[int, CodeReviewResult]:
        meta = meta_by_team[sub.team_number]
        static = static_by_team[sub.team_number]
        return sub.team_number, _review_one(provider, sub, meta, static, cfg)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_do_one, sub): sub.team_number for sub in work}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Code review"):
            team_num, result = future.result()
            results_map[team_num] = result
            if result.success:
                total_input_tokens += result.input_tokens
                total_output_tokens += result.output_tokens
            completed += 1
            if completed % 10 == 0:
                with _save_lock:
                    _save_results_map(results_map, submissions, out_path)

    results = [results_map.get(sub.team_number, CodeReviewResult(team_number=sub.team_number))
               for sub in submissions]
    _save_reviews(results, out_path)

    elapsed = time.time() - start
    reviewed = sum(1 for r in results if r.success)
    click.echo(f"  Reviewed: {reviewed}/{len(results)}")
    click.echo(f"  Tokens: {total_input_tokens:,} in / {total_output_tokens:,} out")
    click.echo(f"  Time: {elapsed:.0f}s")
    click.echo(f"  Saved to {out_path}")

    return results


def _save_reviews(results: list[CodeReviewResult], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump(mode="json") for r in results], f, indent=2, ensure_ascii=False)


def _save_results_map(results_map: dict[int, CodeReviewResult], submissions: list[Submission], path: Path) -> None:
    ordered = [results_map[s.team_number] for s in submissions if s.team_number in results_map]
    _save_reviews(ordered, path)


def _load_reviews_file(path: Path) -> list[CodeReviewResult]:
    with open(path) as f:
        return [CodeReviewResult(**r) for r in json.load(f)]


def load_code_reviews(cfg: ReviewConfig) -> list[CodeReviewResult]:
    """Load previously saved code reviews."""
    path = cfg.data_dir / "code_reviews.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the analyze stage first.")
    return _load_reviews_file(path)

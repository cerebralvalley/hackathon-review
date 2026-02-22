"""Stage 7: Configurable scoring engine."""

from __future__ import annotations

import json
import math
from pathlib import Path

import click
from tqdm import tqdm

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    CodeReviewResult,
    CriterionScore,
    HackathonPeriodFlag,
    ProjectScore,
    RepoMetadata,
    StaticAnalysisResult,
    Submission,
    VideoAnalysisResult,
)


def _log_scale(value: float, midpoint: float, steepness: float = 1.0) -> float:
    """Sigmoid-like scaling: maps value to 0-1 with midpoint at 0.5."""
    if value <= 0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-steepness * (math.log(value + 1) - math.log(midpoint + 1))))


# ---------------------------------------------------------------------------
# Heuristic scoring (fallback when no LLM scores available)
# ---------------------------------------------------------------------------

def _heuristic_impact(sub: Submission, meta: RepoMetadata, static: StaticAnalysisResult) -> float:
    score = 0.0
    desc = sub.description
    score += min(2.0, len(desc.split()) / 80)
    score += _log_scale(meta.files.total_loc, 5000, 1.2) * 2.5
    score += min(1.0, len(static.structure.frameworks_detected) * 0.4)
    if meta.files.has_readme:
        score += 1.0
    deploy = 0
    if static.structure.has_docker:
        deploy += 0.5
    if static.structure.has_ci:
        deploy += 0.5
    if static.structure.has_env_example:
        deploy += 0.5
    score += deploy
    return max(1.0, min(10.0, score))


def _heuristic_ai_use(static: StaticAnalysisResult) -> float:
    raw = static.integration_score
    if raw == 0:
        return 1.0
    base = 1.0 + _log_scale(raw, 60, 1.0) * 7.0
    bonus = 0
    patterns = static.integration_patterns
    if "extended_thinking" in patterns:
        bonus += 0.4
    if "mcp_server" in patterns:
        bonus += 0.3
    if "agentic_pattern" in patterns:
        bonus += 0.3
    if "anthropic_sdk" in patterns or "openai_sdk" in patterns or "gemini_sdk" in patterns:
        bonus += 0.3
    if "tool_use" in patterns:
        bonus += 0.2
    return max(1.0, min(8.0, base + bonus))


def _heuristic_depth(meta: RepoMetadata, static: StaticAnalysisResult) -> float:
    score = 0.0
    commits = meta.git_history.commits_during_hackathon or meta.git_history.total_commits
    score += _log_scale(commits, 50, 1.0) * 2.5
    score += _log_scale(meta.files.total_loc, 10000, 1.0) * 2.0
    if meta.files.has_tests:
        score += 1.0
    if static.structure.has_claude_md:
        score += 0.5
    if meta.files.has_readme:
        score += 0.5
    code_langs = {k: v for k, v in meta.files.languages.items()
                  if k not in {"Markdown", "JSON", "YAML", "TOML"}}
    if len(code_langs) >= 3:
        score += 0.5
    if static.structure.has_docker:
        score += 0.5
    if static.structure.has_ci:
        score += 0.5
    score += _log_scale(meta.files.file_count, 50, 1.0)

    if meta.git_history.is_single_commit_dump:
        score -= 2.0
    if static.is_boilerplate_heavy:
        score -= 2.0
    flag = meta.git_history.hackathon_period_flag
    if flag == HackathonPeriodFlag.PRE_EXISTING_PROJECT:
        score -= 3.0
    elif flag == HackathonPeriodFlag.SIGNIFICANT_PRIOR_WORK:
        score -= 1.5

    return max(1.0, min(10.0, score))


def _heuristic_demo(video: VideoAnalysisResult | None) -> float:
    if not video or not video.download.success:
        return 1.0
    score = 1.0  # baseline for having a video
    dur = video.download.duration_seconds
    if dur < 30:
        score += 0.3
    elif dur < 60:
        score += 1.0
    elif dur <= 200:
        score += 2.5
    else:
        score += 2.0
    return max(1.0, min(8.0, score))


# ---------------------------------------------------------------------------
# Score merging logic
# ---------------------------------------------------------------------------

def _score_one(
    sub: Submission,
    meta: RepoMetadata | None,
    static: StaticAnalysisResult | None,
    code_review: CodeReviewResult | None,
    video: VideoAnalysisResult | None,
    cfg: ReviewConfig,
) -> ProjectScore:
    ps = ProjectScore(
        team_number=sub.team_number,
        team_name=sub.team_name,
        project_name=sub.project_name,
    )

    if not cfg.scoring or not cfg.scoring.criteria:
        return ps

    criteria = cfg.scoring.criteria
    _meta = meta or RepoMetadata(
        team_number=sub.team_number, team_name=sub.team_name,
        project_name=sub.project_name, sanitized_name=sub.sanitized_name,
    )
    _static = static or StaticAnalysisResult(team_number=sub.team_number)

    for crit_name, crit_cfg in criteria.items():
        # Prefer LLM scores if available
        llm_score = None
        if code_review and code_review.success and crit_name in code_review.scores:
            llm_score = code_review.scores[crit_name].score
        if crit_name == "demo" and video and video.analysis_success and "demo" in video.scores:
            llm_score = video.scores["demo"].score

        if llm_score is not None:
            ps.scores[crit_name] = CriterionScore(
                score=llm_score,
                source="llm_review",
            )
        else:
            # Fall back to heuristic
            heuristic_map = {
                "impact": lambda: _heuristic_impact(sub, _meta, _static),
                "ai_use": lambda: _heuristic_ai_use(_static),
                "depth": lambda: _heuristic_depth(_meta, _static),
                "demo": lambda: _heuristic_demo(video),
            }
            fn = heuristic_map.get(crit_name)
            val = fn() if fn else 5.0
            ps.scores[crit_name] = CriterionScore(
                score=round(val, 1),
                source="heuristic",
            )

    # Weighted total
    total = 0.0
    for crit_name, crit_cfg in criteria.items():
        if crit_name in ps.scores:
            total += ps.scores[crit_name].score * crit_cfg.weight
    ps.weighted_total = round(total, 2)

    return ps


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def run_scoring(
    cfg: ReviewConfig,
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    static_results: list[StaticAnalysisResult],
    code_reviews: list[CodeReviewResult],
    video_results: list[VideoAnalysisResult],
) -> list[ProjectScore]:
    """Score all submissions and save to JSON."""
    click.echo("\n--- Stage 7: Scoring ---")

    if not cfg.scoring or not cfg.scoring.criteria:
        click.echo("  Scoring disabled (no scoring config). Skipping.")
        return []

    meta_map = {m.team_number: m for m in repo_metadata}
    static_map = {s.team_number: s for s in static_results}
    review_map = {r.team_number: r for r in code_reviews}
    video_map = {v.team_number: v for v in video_results}

    scores: list[ProjectScore] = []
    for sub in tqdm(submissions, desc="Scoring"):
        s = _score_one(
            sub,
            meta_map.get(sub.team_number),
            static_map.get(sub.team_number),
            review_map.get(sub.team_number),
            video_map.get(sub.team_number),
            cfg,
        )
        scores.append(s)

    scores.sort(key=lambda s: s.weighted_total, reverse=True)

    out_path = cfg.data_dir / "scores.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([s.model_dump(mode="json") for s in scores], f, indent=2, ensure_ascii=False)

    click.echo(f"  Scored {len(scores)} submissions")
    if scores:
        top = scores[0]
        click.echo(f"  Top score: {top.weighted_total:.1f} — {top.project_name} ({top.team_name})")
    click.echo(f"  Saved to {out_path}")

    return scores


def load_scores(cfg: ReviewConfig) -> list[ProjectScore]:
    """Load previously saved scores."""
    path = cfg.data_dir / "scores.json"
    if not path.exists():
        return []
    with open(path) as f:
        return [ProjectScore(**s) for s in json.load(f)]

"""Stage 8: Report generation — per-project reports, leaderboard, flags."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import click

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    CodeReviewResult,
    DemoClassification,
    HackathonPeriodFlag,
    LatenessCategory,
    ProjectFlag,
    ProjectScore,
    RepoMetadata,
    StaticAnalysisResult,
    Submission,
    VideoAnalysisResult,
)


# ---------------------------------------------------------------------------
# Flag collection
# ---------------------------------------------------------------------------

def _collect_flags(
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    video_results: list[VideoAnalysisResult],
    cfg: ReviewConfig,
) -> list[ProjectFlag]:
    flags: list[ProjectFlag] = []
    meta_map = {m.team_number: m for m in repo_metadata}
    video_map = {v.team_number: v for v in video_results}

    for sub in submissions:
        meta = meta_map.get(sub.team_number)
        video = video_map.get(sub.team_number)

        # GitHub issues
        if not sub.github.is_valid:
            flags.append(ProjectFlag(
                team_number=sub.team_number,
                team_name=sub.team_name,
                project_name=sub.project_name,
                flag_type="invalid_github_url",
                description=f"GitHub URL invalid: {', '.join(sub.github.issues)}",
                severity="error",
            ))
        elif meta and not meta.clone_success:
            flags.append(ProjectFlag(
                team_number=sub.team_number,
                team_name=sub.team_name,
                project_name=sub.project_name,
                flag_type="clone_failed",
                description=f"Could not clone repo: {meta.clone_error}",
                severity="error",
            ))

        # Video issues
        if not sub.video.is_valid:
            flags.append(ProjectFlag(
                team_number=sub.team_number,
                team_name=sub.team_name,
                project_name=sub.project_name,
                flag_type="invalid_video_url",
                description=f"Video URL invalid: {', '.join(sub.video.issues)}",
                severity="error",
            ))
        elif video and not video.download.success:
            flags.append(ProjectFlag(
                team_number=sub.team_number,
                team_name=sub.team_name,
                project_name=sub.project_name,
                flag_type="video_download_failed",
                description=f"Could not download video: {video.download.error}",
                severity="error",
            ))

        # Video unrelated to project
        if video and video.analysis_success and not video.is_related_to_project:
            flags.append(ProjectFlag(
                team_number=sub.team_number,
                team_name=sub.team_name,
                project_name=sub.project_name,
                flag_type="video_unrelated",
                description="Video does not appear related to the project description",
                severity="warning",
            ))

        # Hackathon-specific flags
        if cfg.hackathon:
            if sub.timing.lateness_category in (
                LatenessCategory.MODERATELY_LATE,
                LatenessCategory.SIGNIFICANTLY_LATE,
            ):
                flags.append(ProjectFlag(
                    team_number=sub.team_number,
                    team_name=sub.team_name,
                    project_name=sub.project_name,
                    flag_type="late_submission",
                    description=f"Submitted {sub.timing.minutes_late:.0f} min late ({sub.timing.lateness_category.value})",
                    severity="warning",
                ))

            if meta and meta.git_history.hackathon_period_flag in (
                HackathonPeriodFlag.SIGNIFICANT_PRIOR_WORK,
                HackathonPeriodFlag.PRE_EXISTING_PROJECT,
            ):
                flags.append(ProjectFlag(
                    team_number=sub.team_number,
                    team_name=sub.team_name,
                    project_name=sub.project_name,
                    flag_type="git_period_violation",
                    description=f"Git history flag: {meta.git_history.hackathon_period_flag.value} "
                                f"({meta.git_history.commits_before_hackathon} commits before hackathon)",
                    severity="warning",
                ))

            if meta and meta.git_history.is_single_commit_dump:
                flags.append(ProjectFlag(
                    team_number=sub.team_number,
                    team_name=sub.team_name,
                    project_name=sub.project_name,
                    flag_type="single_commit_dump",
                    description="Repository has only a single commit (possible squash or copy-paste)",
                    severity="info",
                ))

    return flags


# ---------------------------------------------------------------------------
# Flags report
# ---------------------------------------------------------------------------

def _write_flags_report(flags: list[ProjectFlag], path: Path) -> None:
    lines = [
        "# Issue Flags Report",
        "",
        f"Total flags: {len(flags)}",
        "",
    ]

    by_type: dict[str, list[ProjectFlag]] = {}
    for f in flags:
        by_type.setdefault(f.flag_type, []).append(f)

    for flag_type, items in sorted(by_type.items()):
        severity = items[0].severity.upper()
        lines.append(f"## {flag_type.replace('_', ' ').title()} [{severity}] ({len(items)})")
        lines.append("")
        lines.append("| # | Team | Project | Details |")
        lines.append("|---|---|---|---|")
        for f in items:
            lines.append(f"| {f.team_number} | {f.team_name[:25]} | {f.project_name[:30]} | {f.description[:80]} |")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Leaderboard CSV
# ---------------------------------------------------------------------------

def _write_leaderboard(
    scores: list[ProjectScore],
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    static_results: list[StaticAnalysisResult],
    path: Path,
) -> None:
    if not scores:
        return

    sub_map = {s.team_number: s for s in submissions}
    meta_map = {m.team_number: m for m in repo_metadata}
    static_map = {s.team_number: s for s in static_results}

    sorted_scores = sorted(scores, key=lambda s: s.weighted_total, reverse=True)

    rows = []
    for rank, ps in enumerate(sorted_scores, 1):
        sub = sub_map.get(ps.team_number)
        meta = meta_map.get(ps.team_number)
        static = static_map.get(ps.team_number)

        row = {
            "rank": rank,
            "team_number": ps.team_number,
            "team_name": ps.team_name,
            "project_name": ps.project_name,
            "weighted_total": ps.weighted_total,
        }
        for crit_name, crit_score in ps.scores.items():
            row[crit_name] = crit_score.score

        if meta:
            row["total_loc"] = meta.files.total_loc
            row["primary_language"] = meta.files.primary_language
            row["commits"] = meta.git_history.total_commits
        if static:
            row["integration_depth"] = static.integration_depth.value
        if sub:
            row["github_url"] = sub.github.original
            row["video_url"] = sub.video.original

        rows.append(row)

    if rows:
        fieldnames = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


# ---------------------------------------------------------------------------
# Per-project reports
# ---------------------------------------------------------------------------

def _write_project_report(
    sub: Submission,
    meta: RepoMetadata | None,
    static: StaticAnalysisResult | None,
    code_review: CodeReviewResult | None,
    video: VideoAnalysisResult | None,
    score: ProjectScore | None,
    flags: list[ProjectFlag],
    path: Path,
) -> None:
    lines = [
        f"# {sub.project_name}",
        f"**Team #{sub.team_number}: {sub.team_name}**",
        "",
    ]

    if score and score.weighted_total > 0:
        lines.append(f"**Score: {score.weighted_total:.1f}/10**")
        lines.append("")

    lines.append(f"**GitHub:** {sub.github.original}")
    lines.append(f"**Video:** {sub.video.original}")
    lines.append("")

    # Flags
    project_flags = [f for f in flags if f.team_number == sub.team_number]
    if project_flags:
        lines.append("## Flags")
        lines.append("")
        for f in project_flags:
            icon = {"error": "!!!", "warning": "!!", "info": "!"}[f.severity]
            lines.append(f"- **[{f.severity.upper()}]** {f.description}")
        lines.append("")

    # Scores
    if score and score.scores:
        lines.append("## Scores")
        lines.append("")
        lines.append("| Criterion | Score | Source |")
        lines.append("|---|---|---|")
        for crit_name, crit_score in score.scores.items():
            lines.append(f"| {crit_name.replace('_', ' ').title()} | {crit_score.score:.1f}/10 | {crit_score.source} |")
        lines.append("")

    # Description
    lines.append("## Description")
    lines.append("")
    lines.append(sub.description if sub.description else "*No description provided.*")
    lines.append("")

    # Code review
    if code_review and code_review.success and code_review.review_text:
        lines.append("## Code Review")
        lines.append("")
        lines.append(code_review.review_text)
        lines.append("")

    # Video analysis
    if video and video.analysis_success:
        lines.append("## Video Analysis")
        lines.append("")
        if video.transcript_summary:
            lines.append(f"**Summary:** {video.transcript_summary}")
            lines.append("")
        lines.append(f"**Demo Classification:** {video.demo_classification.value}")
        if not video.is_related_to_project:
            lines.append("**WARNING:** Video does not appear related to the project.")
        if video.review_text:
            lines.append("")
            lines.append(video.review_text)
        lines.append("")

    # Repo metadata
    if meta and meta.clone_success:
        lines.append("## Repository")
        lines.append("")
        lines.append(f"- **LOC:** {meta.files.total_loc:,}")
        lines.append(f"- **Primary Language:** {meta.files.primary_language}")
        langs = ", ".join(meta.files.languages.keys())
        if langs:
            lines.append(f"- **Languages:** {langs}")
        lines.append(f"- **Commits:** {meta.git_history.total_commits}")
        lines.append(f"- **Has README:** {'Yes' if meta.files.has_readme else 'No'}")
        lines.append(f"- **Has Tests:** {'Yes' if meta.files.has_tests else 'No'}")
        if meta.git_history.hackathon_period_flag.value != "unknown":
            lines.append(f"- **Hackathon Period:** {meta.git_history.hackathon_period_flag.value}")
        lines.append("")

    # AI Integration
    if static and static.integration_patterns:
        lines.append("## AI Integration")
        lines.append("")
        lines.append(f"- **Depth:** {static.integration_depth.value}")
        lines.append("- **Patterns:**")
        for pname, pdata in static.integration_patterns.items():
            lines.append(f"  - {pdata.description} ({pdata.match_count} matches in {len(pdata.files)} files)")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def _write_summary(
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    video_results: list[VideoAnalysisResult],
    scores: list[ProjectScore],
    flags: list[ProjectFlag],
    cfg: ReviewConfig,
    path: Path,
) -> None:
    total = len(submissions)
    cloned = sum(1 for m in repo_metadata if m.clone_success)
    videos_ok = sum(1 for v in video_results if v.download.success)
    analyzed = sum(1 for v in video_results if v.analysis_success)

    lines = [
        "# hackathon-reviewer — Pipeline Summary",
        "",
        f"**Submissions:** {total}",
        f"**Repos cloned:** {cloned}/{total}",
        f"**Videos downloaded:** {videos_ok}/{total}",
        f"**Videos analyzed:** {analyzed}/{total}",
        f"**Flags raised:** {len(flags)}",
        "",
    ]

    if cfg.hackathon and cfg.hackathon.name:
        lines.insert(2, f"**Hackathon:** {cfg.hackathon.name}")

    if scores:
        lines.append("## Top 20")
        lines.append("")
        lines.append("| Rank | Team | Project | Score |")
        lines.append("|---|---|---|---|")
        for i, ps in enumerate(scores[:20], 1):
            lines.append(f"| {i} | {ps.team_name[:25]} | {ps.project_name[:30]} | {ps.weighted_total:.1f} |")
        lines.append("")

    flag_counts: dict[str, int] = {}
    for f in flags:
        flag_counts[f.flag_type] = flag_counts.get(f.flag_type, 0) + 1
    if flag_counts:
        lines.append("## Flag Summary")
        lines.append("")
        for ft, count in sorted(flag_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{ft.replace('_', ' ').title()}:** {count}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------

def run_reporting(
    cfg: ReviewConfig,
    submissions: list[Submission],
    repo_metadata: list[RepoMetadata],
    static_results: list[StaticAnalysisResult],
    code_reviews: list[CodeReviewResult],
    video_results: list[VideoAnalysisResult],
    scores: list[ProjectScore],
) -> None:
    """Generate all reports."""
    click.echo("\n--- Stage 8: Report Generation ---")

    meta_map = {m.team_number: m for m in repo_metadata}
    static_map = {s.team_number: s for s in static_results}
    review_map = {r.team_number: r for r in code_reviews}
    video_map = {v.team_number: v for v in video_results}
    score_map = {s.team_number: s for s in scores}

    # Collect flags
    flags = _collect_flags(submissions, repo_metadata, video_results, cfg)

    # Flags report
    flags_path = cfg.reports_dir / "flags.md"
    _write_flags_report(flags, flags_path)
    click.echo(f"  Flags report: {flags_path} ({len(flags)} flags)")

    # Leaderboard
    if scores:
        lb_path = cfg.reports_dir / "leaderboard.csv"
        _write_leaderboard(scores, submissions, repo_metadata, static_results, lb_path)
        click.echo(f"  Leaderboard: {lb_path}")

    # Per-project reports
    projects_dir = cfg.reports_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    for sub in submissions:
        report_path = projects_dir / f"{sub.sanitized_name}.md"
        _write_project_report(
            sub,
            meta_map.get(sub.team_number),
            static_map.get(sub.team_number),
            review_map.get(sub.team_number),
            video_map.get(sub.team_number),
            score_map.get(sub.team_number),
            flags,
            report_path,
        )
    click.echo(f"  Project reports: {projects_dir}/ ({len(submissions)} files)")

    # Summary
    summary_path = cfg.reports_dir / "summary.md"
    _write_summary(submissions, repo_metadata, video_results, scores, flags, cfg, summary_path)
    click.echo(f"  Summary: {summary_path}")

"""CLI entry point for hackathon-reviewer."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from hackathon_reviewer.config import ReviewConfig, load_config

load_dotenv()


def _build_config(csv: str | None, config: str | None, output: str) -> ReviewConfig:
    """Load YAML config and merge CLI args."""
    cfg = load_config(config)
    if csv:
        cfg.csv_path = Path(csv)
    cfg.output_dir = Path(output)
    cfg.ensure_dirs()
    return cfg


@click.group()
@click.version_option(package_name="hackathon-reviewer")
def main():
    """hackathon-reviewer: Automated hackathon submission analysis."""
    pass


@main.command()
@click.option("--csv", required=True, type=click.Path(exists=True), help="Path to submissions CSV.")
@click.option("--config", default=None, type=click.Path(exists=True), help="Path to config YAML.")
@click.option("--output", default="./output", help="Output directory.")
@click.option("--resume/--no-resume", default=True, help="Skip already-completed work.")
def run(csv: str, config: str | None, output: str, resume: bool):
    """Run the full review pipeline."""
    cfg = _build_config(csv, config, output)

    from hackathon_reviewer.stages.parse import run_parse
    from hackathon_reviewer.stages.clone import run_clone
    from hackathon_reviewer.stages.video import run_video_download
    from hackathon_reviewer.stages.static_analysis import run_static_analysis
    from hackathon_reviewer.stages.code_review import run_code_review
    from hackathon_reviewer.stages.video_analysis import run_video_analysis
    from hackathon_reviewer.stages.scoring import run_scoring
    from hackathon_reviewer.stages.reporting import run_reporting

    click.echo("=" * 60)
    click.echo("  hackathon-reviewer — full pipeline")
    click.echo("=" * 60)

    submissions = run_parse(cfg)
    repo_metadata = run_clone(cfg, submissions, resume=resume)
    video_downloads = run_video_download(cfg, submissions, resume=resume)
    static_results = run_static_analysis(cfg, submissions, repo_metadata)
    code_reviews = run_code_review(cfg, submissions, repo_metadata, static_results, resume=resume)
    video_results = run_video_analysis(cfg, submissions, video_downloads, resume=resume)
    scores = run_scoring(cfg, submissions, repo_metadata, static_results, code_reviews, video_results)
    run_reporting(cfg, submissions, repo_metadata, static_results, code_reviews, video_results, scores)

    click.echo("\n" + "=" * 60)
    click.echo("  Pipeline complete. Reports in: " + str(cfg.reports_dir))
    click.echo("=" * 60)


@main.command()
@click.option("--csv", required=True, type=click.Path(exists=True), help="Path to submissions CSV.")
@click.option("--config", default=None, type=click.Path(exists=True), help="Path to config YAML.")
@click.option("--output", default="./output", help="Output directory.")
def parse(csv: str, config: str | None, output: str):
    """Parse the submissions CSV into structured JSON."""
    cfg = _build_config(csv, config, output)
    from hackathon_reviewer.stages.parse import run_parse
    run_parse(cfg)


@main.command()
@click.option("--config", default=None, type=click.Path(exists=True), help="Path to config YAML.")
@click.option("--output", default="./output", help="Output directory.")
@click.option("--resume/--no-resume", default=True, help="Skip already-cloned repos.")
def clone(config: str | None, output: str, resume: bool):
    """Clone all GitHub repositories."""
    cfg = _build_config(None, config, output)
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.clone import run_clone
    submissions = load_submissions(cfg)
    run_clone(cfg, submissions, resume=resume)


@main.command()
@click.option("--csv", required=True, type=click.Path(exists=True), help="Path to submissions CSV.")
@click.option("--config", default=None, type=click.Path(exists=True), help="Path to config YAML.")
@click.option("--output", default="./output", help="Output directory.")
@click.option("--resume/--no-resume", default=True, help="Skip already-downloaded videos.")
def download(csv: str, config: str | None, output: str, resume: bool):
    """Download all demo videos."""
    cfg = _build_config(csv, config, output)
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.video import run_video_download
    submissions = load_submissions(cfg)
    run_video_download(cfg, submissions, resume=resume)


@main.command()
@click.option("--config", default=None, type=click.Path(exists=True), help="Path to config YAML.")
@click.option("--output", default="./output", help="Output directory.")
@click.option("--resume/--no-resume", default=True, help="Skip already-completed work.")
def analyze(config: str | None, output: str, resume: bool):
    """Run code review and video analysis (requires parse, clone, download first)."""
    cfg = _build_config(None, config, output)
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.clone import load_repo_metadata
    from hackathon_reviewer.stages.video import load_video_downloads
    from hackathon_reviewer.stages.static_analysis import run_static_analysis
    from hackathon_reviewer.stages.code_review import run_code_review
    from hackathon_reviewer.stages.video_analysis import run_video_analysis

    submissions = load_submissions(cfg)
    repo_metadata = load_repo_metadata(cfg)
    video_downloads = load_video_downloads(cfg)
    static_results = run_static_analysis(cfg, submissions, repo_metadata)
    run_code_review(cfg, submissions, repo_metadata, static_results, resume=resume)
    run_video_analysis(cfg, submissions, video_downloads, resume=resume)


@main.command()
@click.option("--config", default=None, type=click.Path(exists=True), help="Path to config YAML.")
@click.option("--output", default="./output", help="Output directory.")
def report(config: str | None, output: str):
    """Generate reports from existing analysis data."""
    cfg = _build_config(None, config, output)
    from hackathon_reviewer.stages.parse import load_submissions
    from hackathon_reviewer.stages.clone import load_repo_metadata
    from hackathon_reviewer.stages.static_analysis import load_static_analysis
    from hackathon_reviewer.stages.code_review import load_code_reviews
    from hackathon_reviewer.stages.video_analysis import load_video_analysis
    from hackathon_reviewer.stages.scoring import run_scoring, load_scores
    from hackathon_reviewer.stages.reporting import run_reporting

    submissions = load_submissions(cfg)
    repo_metadata = load_repo_metadata(cfg)
    static_results = load_static_analysis(cfg)
    code_reviews = load_code_reviews(cfg)
    video_results = load_video_analysis(cfg)
    scores = run_scoring(cfg, submissions, repo_metadata, static_results, code_reviews, video_results)
    run_reporting(cfg, submissions, repo_metadata, static_results, code_reviews, video_results, scores)

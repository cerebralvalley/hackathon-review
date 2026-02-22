"""Stage 2: Clone repositories, extract metadata and git history."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import click
from tqdm import tqdm

from hackathon_reviewer.config import ReviewConfig
from hackathon_reviewer.models import (
    GitHistory,
    HackathonPeriodFlag,
    RepoFiles,
    RepoMetadata,
    Submission,
)
from hackathon_reviewer.utils.git import is_valid_repo, run_git

CLONE_TIMEOUT = 120

SKIP_DIRS = {
    "node_modules", ".git", "vendor", "venv", ".venv", "__pycache__",
    ".next", "dist", "build", ".cache", "target", "coverage",
    ".idea", ".vscode", "env", ".env",
}

SKIP_EXTENSIONS = {
    ".lock", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map", ".min.js", ".min.css",
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
}

LANGUAGE_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".rs": "Rust",
    ".go": "Go", ".java": "Java", ".rb": "Ruby", ".swift": "Swift",
    ".kt": "Kotlin", ".cpp": "C++", ".c": "C", ".cs": "C#",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".vue": "Vue", ".svelte": "Svelte", ".dart": "Dart",
    ".sh": "Shell", ".md": "Markdown", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
}

LOCK_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock", "poetry.lock"}


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

def _clone_repo(clone_url: str, dest_dir: Path) -> tuple[bool, str | None]:
    dest_dir = dest_dir.resolve()
    if dest_dir.exists() and is_valid_repo(dest_dir):
        return True, None

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    rc, _, stderr = run_git(
        ["clone", clone_url, str(dest_dir)],
        str(dest_dir.parent),
        timeout=CLONE_TIMEOUT,
    )
    if rc == 0:
        return True, None
    return False, (stderr.strip()[:200] if stderr else "unknown_error")


# ---------------------------------------------------------------------------
# Repo file metadata
# ---------------------------------------------------------------------------

def _scan_repo_files(repo_dir: Path) -> RepoFiles:
    files = RepoFiles()
    if not repo_dir.exists():
        return files

    lang_loc: dict[str, int] = {}

    for root, dirs, filenames in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            if ext in SKIP_EXTENSIONS or fname in LOCK_FILES:
                continue

            files.file_count += 1

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = sum(1 for line in f if line.strip())
                files.total_loc += lines
                if ext in LANGUAGE_EXTENSIONS:
                    lang = LANGUAGE_EXTENSIONS[ext]
                    lang_loc[lang] = lang_loc.get(lang, 0) + lines
            except OSError:
                pass

    files.languages = dict(sorted(lang_loc.items(), key=lambda x: -x[1]))
    if lang_loc:
        files.primary_language = max(lang_loc, key=lang_loc.get)

    files.has_readme = any(
        (repo_dir / name).exists()
        for name in ["README.md", "readme.md", "README.rst", "README", "README.txt"]
    )

    for root, dirs, filenames in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in filenames:
            lower = fname.lower()
            if ("test" in lower or "spec" in lower) and any(
                lower.endswith(ext) for ext in [".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go"]
            ):
                files.has_tests = True
                break
        if files.has_tests:
            break

    return files


# ---------------------------------------------------------------------------
# Git history analysis
# ---------------------------------------------------------------------------

def _analyze_git_history(repo_dir: Path, cfg: ReviewConfig) -> GitHistory:
    history = GitHistory()
    if not repo_dir.exists():
        return history

    rc, stdout, _ = run_git(["log", "--format=%H|%aI|%an|%s", "--all"], str(repo_dir))
    if rc != 0 or not stdout.strip():
        return history

    commits = []
    authors: set[str] = set()
    for line in stdout.strip().split("\n"):
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commit_hash, date_str, author, message = parts
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                commits.append({"hash": commit_hash, "date": dt, "author": author, "message": message})
                authors.add(author)
            except ValueError:
                pass

    if not commits:
        return history

    commits.sort(key=lambda c: c["date"])

    history.total_commits = len(commits)
    history.first_commit_date = commits[0]["date"].isoformat()
    history.last_commit_date = commits[-1]["date"].isoformat()
    history.commit_authors = list(authors)
    history.is_single_commit_dump = len(commits) == 1

    # Hackathon period verification (only if configured)
    if cfg.hackathon and cfg.hackathon.verify_git_period and cfg.hackathon.start_date and cfg.hackathon.end_date:
        try:
            hack_start = datetime.fromisoformat(cfg.hackathon.start_date)
            deadline_str = cfg.hackathon.deadline_utc or cfg.hackathon.end_date
            hack_end = datetime.fromisoformat(deadline_str.replace("T", " ").split("+")[0])
        except ValueError:
            return history

        before = sum(1 for c in commits if c["date"] < hack_start)
        during = sum(1 for c in commits if hack_start <= c["date"] <= hack_end)
        after = sum(1 for c in commits if c["date"] > hack_end)

        history.commits_before_hackathon = before
        history.commits_during_hackathon = during
        history.commits_after_deadline = after

        total = len(commits)
        if before == 0:
            history.hackathon_period_flag = HackathonPeriodFlag.CLEAN
        elif before <= 3 and before / total < 0.1:
            history.hackathon_period_flag = HackathonPeriodFlag.MINOR_PRIOR_WORK
        elif before / total < 0.5:
            history.hackathon_period_flag = HackathonPeriodFlag.SIGNIFICANT_PRIOR_WORK
        else:
            history.hackathon_period_flag = HackathonPeriodFlag.PRE_EXISTING_PROJECT

    return history


# ---------------------------------------------------------------------------
# Process one submission
# ---------------------------------------------------------------------------

def _process_one(sub: Submission, cfg: ReviewConfig) -> RepoMetadata:
    meta = RepoMetadata(
        team_number=sub.team_number,
        team_name=sub.team_name,
        project_name=sub.project_name,
        sanitized_name=sub.sanitized_name,
    )

    if not sub.github.is_valid or not sub.github.clone_url:
        meta.clone_error = "no_valid_github_url"
        return meta

    repo_dir = cfg.repos_dir / sub.sanitized_name
    success, error = _clone_repo(sub.github.clone_url, repo_dir)
    meta.clone_success = success
    meta.clone_error = error

    if success:
        meta.files = _scan_repo_files(repo_dir)
        meta.git_history = _analyze_git_history(repo_dir, cfg)

    return meta


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def run_clone(cfg: ReviewConfig, submissions: list[Submission], resume: bool = True) -> list[RepoMetadata]:
    """Clone all repos, extract metadata, save to JSON."""
    click.echo("\n--- Stage 2: Clone Repositories ---")

    existing: dict[int, RepoMetadata] = {}
    out_path = cfg.data_dir / "repo_metadata.json"
    if resume and out_path.exists():
        existing = {m.team_number: m for m in _load_metadata_file(out_path)}
        click.echo(f"  Resuming: {len(existing)} already processed")

    results: list[RepoMetadata] = []
    for sub in tqdm(submissions, desc="Cloning repos"):
        if resume and sub.team_number in existing and existing[sub.team_number].clone_success:
            results.append(existing[sub.team_number])
        else:
            results.append(_process_one(sub, cfg))

    cloned = sum(1 for r in results if r.clone_success)
    click.echo(f"  Cloned: {cloned}/{len(results)}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump(mode="json") for r in results], f, indent=2, ensure_ascii=False)
    click.echo(f"  Saved to {out_path}")

    return results


def _load_metadata_file(path: Path) -> list[RepoMetadata]:
    with open(path) as f:
        return [RepoMetadata(**r) for r in json.load(f)]


def load_repo_metadata(cfg: ReviewConfig) -> list[RepoMetadata]:
    """Load previously saved repo metadata."""
    path = cfg.data_dir / "repo_metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the clone stage first.")
    return _load_metadata_file(path)

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
    Contributor,
    GitHistory,
    HackathonPeriodFlag,
    RepoFiles,
    RepoMetadata,
    Submission,
)
from hackathon_reviewer.utils.git import is_valid_repo, run_git

CLONE_TIMEOUT = 120
MAX_CLONE_RETRIES = 2
RETRY_DELAY = 3

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
    import shutil
    import time

    dest_dir = dest_dir.resolve()
    if dest_dir.exists() and is_valid_repo(dest_dir):
        return True, None

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(1 + MAX_CLONE_RETRIES):
        if attempt > 0:
            if dest_dir.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)
            time.sleep(RETRY_DELAY * attempt)

        rc, _, stderr = run_git(
            ["clone", clone_url, str(dest_dir)],
            str(dest_dir.parent),
            timeout=CLONE_TIMEOUT,
        )
        if rc == 0:
            return True, None
        last_error = stderr.strip()[:200] if stderr else "unknown_error"

    return False, last_error


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

# Built-in bot / non-human-author detection. Matched as case-insensitive
# substrings against both author email and name. AI coding assistants are
# treated as bots here because they're tools used *by* the team, not
# teammates: counting them as contributors would inflate team size.
# Hackathon configs can extend via `extra_bot_authors`.
_BUILTIN_BOT_PATTERNS = (
    # Generic CI / app integrations
    "[bot]",
    "dependabot",
    "renovate",
    "github-actions",
    "noreply@github.com",
    "vercel",
    "netlify",
    # AI coding assistants
    "claude-code",
    "noreply@anthropic.com",
    "copilot",
    "github-copilot",
    "cursor-agent",
    "noreply@cursor.so",
    "noreply@openai.com",
    "devin-ai",
    "bolt.new",
    "lovable.dev",
    "v0.dev",
)

# Co-authored-by trailer (RFC 5322-ish "Name <email>"). GitHub credits these
# as contributors on the repo, so we count them too.
_COAUTHOR_RE = re.compile(
    r"^Co-authored-by:\s*(?P<name>.+?)\s*<(?P<email>[^>]+)>",
    re.IGNORECASE | re.MULTILINE,
)


def _is_bot_identity(name: str, email: str, extra_patterns: list[str]) -> bool:
    haystack = f"{name} {email}".lower()
    for pat in (*_BUILTIN_BOT_PATTERNS, *extra_patterns):
        if pat and pat.lower() in haystack:
            return True
    return False


def _identity_key(name: str, email: str) -> str:
    """Canonical key for grouping a person's commits across machines.

    Prefers the email (lowercased) since it's the most stable identifier git
    captures. Falls back to the display name if email is absent or is a
    GitHub `<id+username>@users.noreply.github.com` placeholder, in which
    case the username portion is used instead.
    """
    e = (email or "").strip().lower()
    if e.endswith("@users.noreply.github.com"):
        # 12345+username@... → username
        local = e.split("@", 1)[0]
        if "+" in local:
            local = local.split("+", 1)[1]
        return f"gh:{local}"
    if e:
        return f"email:{e}"
    return f"name:{(name or '').strip().lower()}"


def _analyze_git_history(repo_dir: Path, cfg: ReviewConfig) -> GitHistory:
    history = GitHistory()
    if not repo_dir.exists():
        return history

    # Use NUL-delimited commits with a record separator so commit messages
    # (which may contain newlines and pipes) don't break parsing. Trailing
    # \x1e separates commits, \x1f separates fields within a commit.
    rc, stdout, _ = run_git(
        ["log", "--all", "--pretty=format:%H%x1f%aI%x1f%aN%x1f%aE%x1f%B%x1e"],
        str(repo_dir),
    )
    if rc != 0 or not stdout.strip():
        return history

    extra_bots = list(getattr(cfg.hackathon, "extra_bot_authors", []) or []) if cfg.hackathon else []

    commits = []
    contributors: dict[str, Contributor] = {}
    bot_identities: set[str] = set()
    raw_author_names: set[str] = set()

    for raw in stdout.split("\x1e"):
        rec = raw.strip()
        if not rec:
            continue
        parts = rec.split("\x1f")
        if len(parts) < 5:
            continue
        commit_hash, date_str, author_name, author_email, body = parts
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue

        commits.append({"hash": commit_hash, "date": dt, "author": author_name, "message": body})
        raw_author_names.add(author_name)

        # Primary author
        is_bot = _is_bot_identity(author_name, author_email, extra_bots)
        key = _identity_key(author_name, author_email)
        if is_bot:
            bot_identities.add(author_name or author_email)
        else:
            c = contributors.get(key)
            if c is None:
                contributors[key] = Contributor(
                    name=author_name, email=author_email, commits=1
                )
            else:
                c.commits += 1
                # Keep the longest seen name as the canonical display name.
                if len(author_name) > len(c.name):
                    c.name = author_name

        # Co-authored-by trailers in the commit body
        for m in _COAUTHOR_RE.finditer(body or ""):
            co_name = m.group("name")
            co_email = m.group("email")
            if _is_bot_identity(co_name, co_email, extra_bots):
                bot_identities.add(co_name)
                continue
            ck = _identity_key(co_name, co_email)
            if ck == key:
                # Author co-credited themselves; ignore.
                continue
            c = contributors.get(ck)
            if c is None:
                contributors[ck] = Contributor(
                    name=co_name, email=co_email, coauthored=1
                )
            else:
                c.coauthored += 1

    if not commits:
        return history

    commits.sort(key=lambda c: c["date"])

    # Second-pass dedup: people frequently commit under both their personal
    # email and GitHub's `<id>+username@users.noreply.github.com` form, which
    # have different identity keys. Merge any contributors whose normalized
    # display name matches another and whose commits would otherwise be split.
    def _norm_name(s: str) -> str:
        return " ".join(s.lower().split())

    merged: dict[str, Contributor] = {}
    by_name: dict[str, Contributor] = {}
    for c in contributors.values():
        nname = _norm_name(c.name)
        existing = by_name.get(nname) if nname else None
        if existing is not None:
            existing.commits += c.commits
            existing.coauthored += c.coauthored
            if not existing.email and c.email:
                existing.email = c.email
        else:
            by_name[nname] = c
            merged[id(c)] = c

    history.total_commits = len(commits)
    history.first_commit_date = commits[0]["date"].isoformat()
    history.last_commit_date = commits[-1]["date"].isoformat()
    history.commit_authors = sorted(raw_author_names)
    history.is_single_commit_dump = len(commits) == 1
    history.contributors = sorted(
        merged.values(),
        key=lambda c: (-c.commits, -c.coauthored, c.name.lower()),
    )
    history.bot_authors = sorted(bot_identities)
    history.human_contributor_count = len(merged)

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

def run_clone(
    cfg: ReviewConfig,
    submissions: list[Submission],
    resume: bool = True,
    progress: "Any | None" = None,
) -> list[RepoMetadata]:
    """Clone all repos, extract metadata, save to JSON."""
    click.echo("\n--- Stage 2: Clone Repositories ---")

    existing: dict[int, RepoMetadata] = {}
    out_path = cfg.data_dir / "repo_metadata.json"
    if resume and out_path.exists():
        existing = {m.team_number: m for m in _load_metadata_file(out_path)}
        click.echo(f"  Resuming: {len(existing)} already processed")

    total = len(submissions)
    results: list[RepoMetadata] = []
    for i, sub in enumerate(tqdm(submissions, desc="Cloning repos"), 1):
        if resume and sub.team_number in existing and existing[sub.team_number].clone_success:
            results.append(existing[sub.team_number])
        else:
            meta = _process_one(sub, cfg)
            results.append(meta)
            if not meta.clone_success and progress:
                progress.add_failure(sub.team_number, sub.team_name, sub.project_name, meta.clone_error or "unknown")
        if progress:
            progress.update(i, total, sub.project_name)

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

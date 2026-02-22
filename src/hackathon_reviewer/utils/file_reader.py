"""Smart file reading for LLM context — prioritizes key files, truncates intelligently."""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", "vendor", "venv", ".venv", "__pycache__",
    ".next", "dist", "build", ".cache", "target", "coverage",
    ".idea", ".vscode", "env", ".env",
}

PRIORITY_FILES = ["README.md", "CLAUDE.md", ".claude/settings.json"]

KEY_ENTRY_POINTS = {
    "main.py", "app.py", "index.ts", "index.js", "server.py", "server.ts",
    "main.ts", "main.js", "run.py", "cli.py",
}

KEY_KEYWORDS = {"claude", "anthropic", "agent", "mcp", "llm", "ai"}

CODE_EXTENSIONS = {".py", ".ts", ".js", ".tsx", ".jsx", ".md", ".rs", ".go"}


def read_key_files(repo_dir: Path, max_chars: int = 20000) -> str:
    """Read key source files from a repo, formatted for LLM context."""
    if not repo_dir.exists():
        return "(repo not available)"

    interesting_files: list[str] = []

    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            fpath = Path(root) / f
            rel = str(fpath.relative_to(repo_dir))

            if any(kw in f.lower() for kw in KEY_KEYWORDS):
                if fpath.suffix in CODE_EXTENSIONS:
                    interesting_files.append(rel)

            if f in KEY_ENTRY_POINTS:
                interesting_files.append(rel)

    agents_dir = repo_dir / ".claude" / "agents"
    if agents_dir.exists():
        for f in agents_dir.glob("*.md"):
            interesting_files.append(str(f.relative_to(repo_dir)))

    skills_dir = repo_dir / ".claude" / "skills"
    if skills_dir.exists():
        for f in skills_dir.rglob("*.md"):
            interesting_files.append(str(f.relative_to(repo_dir)))

    all_files = PRIORITY_FILES + sorted(set(interesting_files))
    content = ""
    for rel_path in all_files:
        fpath = repo_dir / rel_path
        if fpath.exists() and fpath.is_file():
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
                if len(text) > 4000:
                    text = text[:4000] + "\n... (truncated)"
                content += f"\n### {rel_path}\n```\n{text}\n```\n"
                if len(content) > max_chars:
                    break
            except Exception:
                pass

    return content if content else "(no key files found)"

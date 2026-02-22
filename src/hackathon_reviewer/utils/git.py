"""Git command helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: str | Path, timeout: int = 60) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def is_valid_repo(path: Path) -> bool:
    rc, _, _ = run_git(["status"], path)
    return rc == 0

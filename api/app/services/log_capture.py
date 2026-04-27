"""Per-stage log capture.

Stages in `hackathon_reviewer.stages.*` write user-facing progress via
`click.echo` (stdout) and `tqdm` (stderr). To surface those messages in
the web UI, we tee both streams into a per-stage log file for the duration
of the stage. Pipeline stages run sequentially in a single worker thread,
so a global stdout/stderr swap is safe here.
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Strip ANSI escape sequences for cleaner stored logs.
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class _Tee(io.TextIOBase):
    """Write to two streams; flush both on every write.

    The "primary" stream is the original stdout/stderr (terminal); we pass
    everything through unmodified so the user's terminal still sees
    ANSI-colored, carriage-return-rewriting progress bars. The "secondary"
    stream is the per-stage log file; we strip ANSI escape codes before
    writing so the persisted log is readable.
    """

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def write(self, s: str) -> int:
        n = self._primary.write(s)
        try:
            self._secondary.write(_ANSI_RE.sub("", s))
            self._secondary.flush()
        except Exception:
            pass
        try:
            self._primary.flush()
        except Exception:
            pass
        return n

    def flush(self) -> None:
        for stream in (self._primary, self._secondary):
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        try:
            return bool(self._primary.isatty())
        except Exception:
            return False


@contextmanager
def capture_stage(log_path: Path, stage: str):
    """Tee stdout and stderr into `log_path` for the duration of the block.

    Overwrites the file each call so re-runs (e.g., resume) start fresh.
    Always restores the original streams even on exception.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    f = open(log_path, "w", encoding="utf-8", buffering=1)
    f.write(f"=== Stage: {stage} (started {started}) ===\n")
    f.flush()

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = _Tee(original_stdout, f)
    sys.stderr = _Tee(original_stderr, f)
    try:
        yield
    except Exception as exc:
        f.write(f"\n=== ERROR: {type(exc).__name__}: {exc} ===\n")
        f.flush()
        raise
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        ended = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            f.write(f"\n=== Finished {ended} ===\n")
            f.flush()
        finally:
            f.close()

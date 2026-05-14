"""Per-session log capture.

The Windows .exe is a GUI app (`console=False`), so stdout and stderr go
nowhere when launched from Explorer. Without this, a crash leaves the
user with a dialog saying "the app stopped working" and no traceback to
report. With this, every session writes a timestamped log file to a
known location under the user's local app data; uncaught exceptions go
in too via a sys.excepthook.

Public API:
    install(stream_name: str) -> Path
        Wire up the capture. Returns the log file's path so callers can
        surface it in the UI ("Help -> Open Log Folder").

    log_dir() -> Path
        The directory log files live in. Created on first install().

The capture is deliberately minimal: a tee that writes to a file in
addition to the existing stream. This keeps PowerShell/terminal users'
existing debugging experience intact while giving Explorer-launched
sessions somewhere to send their output.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import IO


_APP_NAME = "CortexPortfolio"
_KEEP_RECENT = 10           # prune logs older than the most recent N
_log_file: IO | None = None  # held open for the lifetime of the process


def log_dir() -> Path:
    """Per-OS log directory. Created on demand."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA")
                    or os.path.expanduser("~/AppData/Local"))
    elif sys.platform == "darwin":
        base = Path(os.path.expanduser("~/Library/Logs"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME")
                    or os.path.expanduser("~/.local/state"))
    d = base / _APP_NAME / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prune_old_logs(d: Path, *, keep: int) -> None:
    """Delete all but the most recent `keep` files in `d`. Silent on errors:
    log pruning failing must not break the app."""
    try:
        candidates = sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix == ".log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in candidates[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass


class _Tee:
    """File-like object writing to two streams. Errors on either stream are
    silenced -- this object lives inside sys.stdout/stderr, so a write
    failure must never propagate or it would mask the real output."""

    def __init__(self, primary: IO, secondary: IO | None) -> None:
        self._primary = primary
        self._secondary = secondary

    def write(self, data) -> int:
        try:
            self._primary.write(data)
        except Exception:
            pass
        if self._secondary is not None:
            try:
                self._secondary.write(data)
            except Exception:
                pass
        return len(data) if isinstance(data, str) else 0

    def flush(self) -> None:
        for s in (self._primary, self._secondary):
            if s is None:
                continue
            try:
                s.flush()
            except Exception:
                pass

    # A few attributes Python code occasionally pokes at on stdout/stderr.
    def isatty(self) -> bool:
        try:
            return bool(self._secondary and self._secondary.isatty())
        except Exception:
            return False

    @property
    def encoding(self) -> str:
        return getattr(self._secondary, "encoding", "utf-8") or "utf-8"


def install(stream_name: str = "session") -> Path:
    """Install stdout/stderr capture for the current process.

    `stream_name` is a label that goes in the log filename ("editor",
    "cli"). Returns the path of the log file being written.

    Safe to call more than once; subsequent calls are no-ops.
    """
    global _log_file
    if _log_file is not None:
        # Already installed. Return the existing file's path.
        return Path(_log_file.name)

    d = log_dir()
    _prune_old_logs(d, keep=_KEEP_RECENT)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = d / f"{stream_name}_{ts}.log"
    # Line-buffered (buffering=1) so a crash mid-write still flushes the
    # most recent line. Crucial for debugging crashes.
    _log_file = open(log_path, "w", encoding="utf-8", buffering=1)

    # Header for context. Easier to diagnose a bug report when you know
    # which version produced the log.
    _log_file.write(f"=== {stream_name} session log ===\n")
    _log_file.write(f"Started:  {datetime.now().isoformat()}\n")
    _log_file.write(f"Platform: {sys.platform}\n")
    _log_file.write(f"Python:   {sys.version.splitlines()[0]}\n")
    _log_file.write(f"Executable: {sys.executable}\n")
    _log_file.write(f"Argv:     {sys.argv}\n")
    _log_file.write("===\n")
    _log_file.flush()

    # Tee. Original streams might be None when launched from Explorer
    # with console=False; in that case the log file is the only sink.
    sys.stdout = _Tee(_log_file, sys.stdout)
    sys.stderr = _Tee(_log_file, sys.stderr)

    # Capture uncaught exceptions. Default hook still runs afterwards so
    # any user-facing dialog (PyQt's "windowed traceback") still appears.
    _previous_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        try:
            traceback.print_exception(exc_type, exc_value, exc_tb,
                                      file=sys.stderr)
            sys.stderr.flush()
        finally:
            _previous_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    return log_path

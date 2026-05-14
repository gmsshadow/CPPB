"""Tests for the session log capture mechanism.

The mechanism is small but easy to subtly break: regressions could mean
crashes go unlogged after distribution. Worth a few quick checks.
"""
import sys
from pathlib import Path

import pytest

from cortex_portfolio import _session_log


@pytest.fixture(autouse=True)
def isolated_log_dir(tmp_path, monkeypatch):
    """Redirect log_dir() to a tmp_path. Also reset the singleton so each
    test gets a fresh install."""
    monkeypatch.setattr(_session_log, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(_session_log, "_log_file", None, raising=False)
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    saved_hook = sys.excepthook
    yield tmp_path
    sys.stdout, sys.stderr = saved_stdout, saved_stderr
    sys.excepthook = saved_hook


class TestInstall:
    def test_creates_log_file_with_label(self, isolated_log_dir):
        path = _session_log.install("editor")
        assert path.parent == isolated_log_dir
        assert path.name.startswith("editor_")
        assert path.name.endswith(".log")
        assert path.exists()

    def test_writes_header(self, isolated_log_dir):
        path = _session_log.install("cli")
        content = path.read_text(encoding="utf-8")
        assert "session log" in content
        assert sys.version.splitlines()[0] in content

    def test_captures_stdout(self, isolated_log_dir):
        path = _session_log.install("editor")
        print("hello from a test")
        sys.stdout.flush()
        assert "hello from a test" in path.read_text(encoding="utf-8")

    def test_captures_stderr(self, isolated_log_dir):
        path = _session_log.install("editor")
        print("an error happened", file=sys.stderr)
        sys.stderr.flush()
        assert "an error happened" in path.read_text(encoding="utf-8")

    def test_install_is_idempotent(self, isolated_log_dir):
        first = _session_log.install("editor")
        second = _session_log.install("editor")
        assert first == second  # no new file


class TestPruning:
    def test_keeps_only_recent_logs(self, tmp_path, monkeypatch):
        # Make 15 fake log files with increasing mtimes
        import time
        for i in range(15):
            p = tmp_path / f"editor_2026010{i:02d}_120000.log"
            p.write_text("x")
            # Force distinct mtimes
            import os
            os.utime(p, (1000 + i, 1000 + i))

        _session_log._prune_old_logs(tmp_path, keep=10)

        remaining = sorted(tmp_path.iterdir(), key=lambda p: p.stat().st_mtime)
        assert len(remaining) == 10
        # The 10 most recent are kept (mtimes 1005..1014)
        assert {p.stat().st_mtime for p in remaining} == set(range(1005, 1015))

    def test_pruning_survives_locked_files(self, tmp_path):
        # Trying to delete a non-existent file should silently succeed.
        # We don't have an easy way to simulate locked files cross-platform,
        # but the function should not throw under any normal error.
        (tmp_path / "editor_old.log").write_text("x")
        _session_log._prune_old_logs(tmp_path, keep=0)
        # Worst case: file deleted. Best case: silently skipped. Either is
        # fine -- what matters is "no exception escapes".


class TestExceptHook:
    def test_uncaught_exceptions_are_logged(self, isolated_log_dir):
        path = _session_log.install("editor")
        try:
            raise ValueError("simulated crash for testing")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        sys.stderr.flush()
        content = path.read_text(encoding="utf-8")
        assert "ValueError" in content
        assert "simulated crash for testing" in content
        assert "Traceback" in content

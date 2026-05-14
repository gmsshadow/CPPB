"""Editor app entry point.

Run with:
    python -m cortex_portfolio.editor
or, after installing with the [editor] extra:
    cortex-portfolio-editor
"""
# Silence GLib-GIO startup warnings on Windows. Must come before any import
# that pulls WeasyPrint -- main_window does, transitively. See cli.py for
# the same dance.
import os as _os
_os.environ.setdefault("GIO_USE_VFS", "local")
_os.environ.setdefault("G_MESSAGES_DEBUG", "")

# Capture per-session stdout/stderr to a log file under the user's local
# app data. Critical for Explorer-launched .exe sessions where there is
# no console attached -- without this, a crash leaves the user with
# nothing to send back as a bug report. Must happen before any other
# code that might emit warnings/errors we want captured.
from .. import _session_log as _session_log_module
_LOG_PATH = _session_log_module.install("editor")

import sys

from PyQt6.QtWidgets import QApplication

from cortex_portfolio.editor.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

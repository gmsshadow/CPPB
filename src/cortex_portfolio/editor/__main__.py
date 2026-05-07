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

import sys

from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Editor app entry point.

Run with:
    python -m cortex_portfolio.editor
or, after installing with the [editor] extra:
    cortex-portfolio-editor
"""
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

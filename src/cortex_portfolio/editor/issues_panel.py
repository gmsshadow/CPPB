"""Right-pane issues panel.

Shows the current validation result. Errors first, warnings second, with
the issue path on a small line and the message below. Clicking an issue
emits a signal so the main window can jump the section list there.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..validate import Issue, split


# Colors for the small severity tag chip in front of each issue.
_TAG_STYLE = {
    "error":   "background:#a01818; color:white; padding:1px 6px; border-radius:3px;",
    "warning": "background:#b58a00; color:white; padding:1px 6px; border-radius:3px;",
}


# Patterns that match issue paths -> (kind, ps_id) tuple for navigation.
_PATH_RE = re.compile(
    r"^character\.prime_sets\.(?P<ps>[A-Za-z0-9_]+)"
)
_EXTRAS_RE = re.compile(
    r"^character\.extras\.(?P<which>stress|trauma|milestones|plot_points)"
)


def _kind_id_for_path(path: str) -> tuple[str, str] | None:
    """Map a validation path to (kind, id) for the section list, or None."""
    if path.startswith("character.identity") or path.startswith("character.game_definition") \
            or path.startswith("character.actor_type"):
        return ("identity", "")
    m = _PATH_RE.match(path)
    if m:
        return ("prime_set", m.group("ps"))
    m = _EXTRAS_RE.match(path)
    if m:
        which = m.group("which")
        if which in ("stress", "trauma"):
            return ("stress", "")
        if which == "milestones":
            return ("milestones", "")
        if which == "plot_points":
            return ("notes", "")
    if path == "character.notes":
        return ("notes", "")
    return None


class IssuesPanel(QWidget):
    issueClicked = pyqtSignal(str, str)  # kind, id (for section navigation)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(280)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        head = QHBoxLayout()
        head.addWidget(QLabel("<b>Issues</b>"))
        head.addStretch(1)
        self._summary = QLabel("\u2014")
        self._summary.setStyleSheet("color: #666;")
        head.addWidget(self._summary)
        outer.addLayout(head)

        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._on_clicked)
        outer.addWidget(self._list, 1)

    # ------------------------------------------------------------------
    def set_issues(self, issues: list[Issue]) -> None:
        self._list.clear()
        if not issues:
            self._summary.setText('<span style="color:#1e7e34;">no issues</span>')
            return

        errs, warns = split(issues)
        parts = []
        if errs:
            parts.append(
                f'<span style="color:#a01818;">{len(errs)} error{"s" if len(errs) != 1 else ""}</span>'
            )
        if warns:
            parts.append(
                f'<span style="color:#b58a00;">{len(warns)} warning{"s" if len(warns) != 1 else ""}</span>'
            )
        self._summary.setText("  /  ".join(parts))

        for issue in errs + warns:
            self._list.addItem(self._make_item(issue))

    # ------------------------------------------------------------------
    def _make_item(self, issue: Issue) -> QListWidgetItem:
        # Plain QListWidgetItem with two lines of text. List items handle
        # their own sizing automatically -- no custom-widget sizing dance.
        tag = "ERROR" if issue.is_error() else "warn"
        text = f"[{tag}] {issue.path}\n   {issue.message}"
        item = QListWidgetItem(text)
        if issue.is_error():
            item.setForeground(Qt.GlobalColor.darkRed)
        else:
            item.setForeground(Qt.GlobalColor.darkYellow)
        item.setData(Qt.ItemDataRole.UserRole, issue.path)
        return item

    def _on_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        target = _kind_id_for_path(path)
        if target is not None:
            self.issueClicked.emit(*target)

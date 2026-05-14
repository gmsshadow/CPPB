"""Standalone window for editing game definitions.

Opened from the character editor's File menu. Tree-based navigation on the
left (game / actor types / prime sets / extras), stacked forms in the
centre, IssuesPanel on the right. Reuses the validator and the issues
panel from the character editor.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..validate import validate, split
from .game_def_forms import (
    ActorTypeForm,
    ExtrasForm,
    GameForm,
    PrimeSetForm,
)
from .issues_panel import IssuesPanel


# Tree-node payload: a (kind, *path) tuple stored in UserRole.
# kind values:
#   "game"             -> root
#   "actor_type"       -> path = (actor_type_id,)
#   "prime_sets"       -> path = (actor_type_id,) -- the parent group
#   "prime_set"        -> path = (actor_type_id, ps_id)
#   "extras"           -> path = (actor_type_id,)
PAYLOAD_ROLE = Qt.ItemDataRole.UserRole + 1


def _empty_game_def() -> dict:
    """A minimal-but-valid starter game definition."""
    return {
        "id": "new_game",
        "name": "New Game",
        "version": "0.1.0",
        "dice_pool": ["d4", "d6", "d8", "d10", "d12"],
        "actor_types": {
            "character": {
                "label": "Character",
                "prime_sets": [],
                "extras": {
                    "milestones":  {"enabled": True,  "icon": "medal"},
                    "stress":      {"enabled": True,
                                    "tracks": [
                                        {"id": "physical", "label": "Physical"},
                                        {"id": "mental",   "label": "Mental"},
                                    ],
                                    "trauma_enabled": True},
                    "plot_points": {"enabled": True,  "starting": 1, "icon": "coins"},
                },
            },
        },
    }


def _seed_prime_set(ps_id: str) -> dict:
    """Reasonable starting shape for a freshly added prime set."""
    return {
        "id": ps_id,
        "label": ps_id.replace("_", " ").title(),
        "icon": "scroll",
        "settings": {
            "has_label": True,
            "has_dice":  True,
        },
    }


# ===========================================================================
# Main window
# ===========================================================================

class GameDefWindow(QMainWindow):
    """Editor for a single game-definition file."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Game Definition Editor")
        self.resize(1400, 900)

        # ----- State ---------------------------------------------------
        self._game: dict = _empty_game_def()
        self._path: Path | None = None
        self._dirty: bool = True
        self._form_cache: dict[tuple, QWidget] = {}

        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(150)
        self._validate_timer.timeout.connect(self._run_validation)

        # ----- UI ------------------------------------------------------
        self._build_menu()
        self._build_central()
        self.setStatusBar(QStatusBar())
        self._refresh_tree()
        self._update_window_title()
        self._schedule_validate()

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")

        act_new = QAction("&New Game Definition", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._on_new)
        file_menu.addAction(act_new)

        act_open = QAction("&Open\u2026", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._on_open)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_save = QAction("&Save", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._on_save)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save &As\u2026", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(act_save_as)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ----- Left: tree ---------------------------------------------
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(220)
        self._tree.itemSelectionChanged.connect(self._on_selection)
        # Right-click context menu (add / remove prime sets)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_menu)
        splitter.addWidget(self._tree)

        # ----- Centre: stacked forms ----------------------------------
        self._stack = QStackedWidget()
        # Default placeholder while the tree warms up.
        from PyQt6.QtWidgets import QLabel
        placeholder = QLabel("Select something on the left to edit it.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #777; padding: 40px;")
        self._stack.addWidget(placeholder)
        splitter.addWidget(self._stack)

        # ----- Right: issues -----------------------------------------
        self._issues = IssuesPanel()
        # Issue clicks don't navigate here yet -- the path-to-tree mapping
        # for game-def issues isn't 1:1, so we leave navigation off for now.
        splitter.addWidget(self._issues)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 800, 360])
        self.setCentralWidget(splitter)

    # ==================================================================
    # Tree management
    # ==================================================================
    def _refresh_tree(self, select: tuple | None = None) -> None:
        """Rebuild the tree from the current game def. Optionally re-select
        a previously-known node by its (kind, *path) tuple."""
        self._tree.blockSignals(True)
        try:
            self._tree.clear()

            # Game root
            game_item = QTreeWidgetItem(["Game definition"])
            game_item.setData(0, PAYLOAD_ROLE, ("game",))
            self._tree.addTopLevelItem(game_item)

            for at_id, at_def in (self._game.get("actor_types") or {}).items():
                at_label = at_def.get("label", at_id)
                at_item = QTreeWidgetItem([f"{at_label}   ({at_id})"])
                at_item.setData(0, PAYLOAD_ROLE, ("actor_type", at_id))
                self._tree.addTopLevelItem(at_item)

                ps_group = QTreeWidgetItem(["Prime sets"])
                ps_group.setData(0, PAYLOAD_ROLE, ("prime_sets", at_id))
                ps_group.setForeground(0, Qt.GlobalColor.darkGray)
                at_item.addChild(ps_group)

                for ps in (at_def.get("prime_sets") or []):
                    ps_id = ps.get("id", "")
                    label = ps.get("label", ps_id) or ps_id
                    ps_item = QTreeWidgetItem([label])
                    ps_item.setData(0, PAYLOAD_ROLE, ("prime_set", at_id, ps_id))
                    ps_group.addChild(ps_item)

                ex_item = QTreeWidgetItem(["Extras"])
                ex_item.setData(0, PAYLOAD_ROLE, ("extras", at_id))
                at_item.addChild(ex_item)

            # Default expansion
            self._tree.expandAll()
        finally:
            self._tree.blockSignals(False)

        # Restore selection if requested.
        target = select or ("game",)
        self._select_payload(target)

    def _update_tree_labels(self) -> None:
        """Refresh tree node labels in place without rebuilding the tree.

        Called from _on_data_changed on every keystroke. Critical that this
        does NOT call clear() or setCurrentItem() -- both reset focus on
        whatever input the user is typing in, causing the bouncing-cursor
        / backwards-typing bugs we hit in the character editor too.

        Only labels are updated; id changes don't propagate (the tree's
        payload tuples are keyed by id, and we'd need to rewire them on
        every keystroke otherwise). On save+reopen everything resyncs,
        which is the intended UX for renames.
        """
        actor_types = self._game.get("actor_types") or {}
        for item in self._iter_items():
            payload = item.data(0, PAYLOAD_ROLE)
            if not payload:
                continue
            kind = payload[0]

            if kind == "actor_type":
                at_id = payload[1]
                at_def = actor_types.get(at_id) or {}
                label = at_def.get("label", at_id)
                item.setText(0, f"{label}   ({at_id})")

            elif kind == "prime_set":
                at_id, ps_id = payload[1], payload[2]
                at_def = actor_types.get(at_id) or {}
                ps = next(
                    (p for p in (at_def.get("prime_sets") or [])
                     if p.get("id") == ps_id),
                    None,
                )
                if ps is not None:
                    item.setText(0, ps.get("label", ps_id) or ps_id)
            # game / prime_sets group / extras nodes have static labels.

    def _select_payload(self, payload: tuple) -> None:
        for item in self._iter_items():
            if item.data(0, PAYLOAD_ROLE) == payload:
                self._tree.setCurrentItem(item)
                return
        # Fall back to the root if not found.
        if self._tree.topLevelItemCount():
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _iter_items(self):
        """Walk every item in the tree, depth-first."""
        def walk(item: QTreeWidgetItem):
            yield item
            for i in range(item.childCount()):
                yield from walk(item.child(i))
        for i in range(self._tree.topLevelItemCount()):
            yield from walk(self._tree.topLevelItem(i))

    # ==================================================================
    # Selection -> form
    # ==================================================================
    def _on_selection(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        payload = item.data(0, PAYLOAD_ROLE)
        if not payload:
            return

        form = self._get_form(payload)
        if form is None:
            return

        # Push the latest data into the form before showing it.
        self._load_into_form(payload, form)
        idx = self._stack.indexOf(form)
        if idx < 0:
            idx = self._stack.addWidget(form)
        self._stack.setCurrentIndex(idx)

    def _get_form(self, payload: tuple) -> QWidget | None:
        if payload in self._form_cache:
            return self._form_cache[payload]

        kind = payload[0]
        form: QWidget | None = None
        if kind == "game":
            form = GameForm()
        elif kind == "actor_type":
            form = ActorTypeForm(payload[1])
        elif kind == "prime_sets":
            # The "Prime sets" group itself isn't directly editable -- show
            # a placeholder hinting at the right-click menu.
            from PyQt6.QtWidgets import QLabel
            label = QLabel(
                "<p>This actor type's prime sets are listed below.</p>"
                "<p><i>Right-click here to add a prime set, or right-click "
                "an existing prime set to remove it.</i></p>"
            )
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            label.setStyleSheet("padding: 40px; color: #555;")
            label.setWordWrap(True)
            self._form_cache[payload] = label
            return label
        elif kind == "prime_set":
            form = PrimeSetForm()
        elif kind == "extras":
            form = ExtrasForm()
        else:
            return None

        # Connect dataChanged so edits flow back through the window.
        form.dataChanged.connect(lambda _: self._on_data_changed(payload))

        # Wrap the form in a scroll area. Forms like a PrimeSetForm with a
        # long predefined-items list, or a GameForm with the full theme
        # picker, can easily exceed the centre pane's height -- without
        # this, the overflow is just clipped and unreachable. The cache
        # holds the QScrollArea; _load_into_form unwraps via .widget() to
        # reach the real form for set_data() calls.
        scroll = QScrollArea()
        scroll.setWidget(form)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._form_cache[payload] = scroll
        return scroll

    def _load_into_form(self, payload: tuple, form: QWidget) -> None:
        # _get_form caches real forms wrapped in a QScrollArea; unwrap to
        # reach the actual form widget that carries set_data(). The
        # "prime_sets" group placeholder is a bare QLabel (no set_data,
        # and the kind-dispatch below skips it anyway).
        if isinstance(form, QScrollArea):
            form = form.widget()
        kind = payload[0]
        if kind == "game":
            form.set_data(self._game)
        elif kind == "actor_type":
            at = self._game.setdefault("actor_types", {}).setdefault(payload[1], {})
            form.set_data(at)
        elif kind == "prime_set":
            at_id, ps_id = payload[1], payload[2]
            ps = self._find_prime_set(at_id, ps_id)
            if ps is not None:
                form.set_data(ps)
        elif kind == "extras":
            at = self._game.setdefault("actor_types", {}).setdefault(payload[1], {})
            ex = at.setdefault("extras", {})
            form.set_data(ex)

    def _find_prime_set(self, at_id: str, ps_id: str) -> dict | None:
        for ps in (self._game["actor_types"].get(at_id, {}).get("prime_sets") or []):
            if ps.get("id") == ps_id:
                return ps
        return None

    # ==================================================================
    # Edits propagate here
    # ==================================================================
    def _on_data_changed(self, payload: tuple) -> None:
        # Forms mutate their loaded dicts in place, which are the same dicts
        # nested inside self._game. So no copying back is required -- just
        # mark dirty, possibly refresh tree labels, and re-validate.
        self._dirty = True
        self._update_window_title()

        # IMPORTANT: do NOT call _refresh_tree() here. That clears the tree
        # and re-selects, which steals focus from the input the user is
        # typing in (causes the bouncing-cursor / backwards-typing bugs we
        # already hit in the character editor's main_window). _update_tree_
        # labels updates label text in place without touching selection.
        kind = payload[0]
        if kind in ("actor_type", "prime_set", "game"):
            self._update_tree_labels()

        self._schedule_validate()

    # ==================================================================
    # Tree context menu (add / remove prime sets)
    # ==================================================================
    def _on_tree_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return
        payload = item.data(0, PAYLOAD_ROLE)
        if not payload:
            return

        menu = QMenu(self)
        kind = payload[0]

        if kind in ("actor_type", "prime_sets"):
            at_id = payload[1]
            act = QAction("+ Add prime set\u2026", self)
            act.triggered.connect(lambda: self._add_prime_set(at_id))
            menu.addAction(act)

        if kind == "prime_set":
            at_id, ps_id = payload[1], payload[2]
            act = QAction(f"Remove prime set '{ps_id}'", self)
            act.triggered.connect(lambda: self._remove_prime_set(at_id, ps_id))
            menu.addAction(act)

        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _add_prime_set(self, at_id: str) -> None:
        ps_id, ok = QInputDialog.getText(
            self, "Add Prime Set",
            "ID for the new prime set (snake_case, must be unique):",
        )
        if not ok or not ps_id:
            return
        ps_id = ps_id.strip()
        prime_sets = self._game.setdefault("actor_types", {}) \
            .setdefault(at_id, {}).setdefault("prime_sets", [])
        if any(ps.get("id") == ps_id for ps in prime_sets):
            QMessageBox.warning(
                self, "Duplicate ID",
                f"A prime set with ID '{ps_id}' already exists in this actor type.",
            )
            return
        prime_sets.append(_seed_prime_set(ps_id))
        self._dirty = True
        self._update_window_title()
        self._refresh_tree(select=("prime_set", at_id, ps_id))
        self._schedule_validate()

    def _remove_prime_set(self, at_id: str, ps_id: str) -> None:
        reply = QMessageBox.question(
            self, "Remove prime set?",
            f"Remove prime set '{ps_id}' from actor type '{at_id}'?\n"
            "Characters using this prime set will still load, but data "
            "for it will surface as a validation warning.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        prime_sets = self._game.get("actor_types", {}).get(at_id, {}).get("prime_sets") or []
        self._game["actor_types"][at_id]["prime_sets"] = [
            ps for ps in prime_sets if ps.get("id") != ps_id
        ]
        # Drop the form cache entry for the removed prime set.
        self._form_cache.pop(("prime_set", at_id, ps_id), None)
        self._dirty = True
        self._update_window_title()
        self._refresh_tree(select=("prime_sets", at_id))
        self._schedule_validate()

    # ==================================================================
    # File I/O
    # ==================================================================
    def _on_new(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._game = _empty_game_def()
        self._path = None
        self._dirty = True
        self._form_cache.clear()
        self._refresh_tree()
        self._update_window_title()
        self._schedule_validate()

    def _on_open(self) -> None:
        if not self._confirm_discard_changes():
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Game Definition", "", "JSON files (*.json)"
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            self._game = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Open failed", f"Could not load:\n{e}")
            return
        self._path = path
        self._dirty = False
        self._form_cache.clear()
        self._refresh_tree()
        self._update_window_title()
        self._schedule_validate()

    def _on_save(self) -> None:
        if self._path is None:
            self._on_save_as()
            return
        self._write(self._path)

    def _on_save_as(self) -> None:
        suggested = ""
        if self._path is not None:
            suggested = str(self._path)
        elif self._game.get("id"):
            suggested = f"{self._game['id']}.game.json"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Game Definition", suggested, "JSON files (*.json)"
        )
        if not path_str:
            return
        self._write(Path(path_str))

    def _write(self, path: Path) -> None:
        try:
            path.write_text(
                json.dumps(self._game, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            QMessageBox.critical(self, "Save failed", f"Could not save:\n{e}")
            return
        self._path = path
        self._dirty = False
        self._update_window_title()
        self.statusBar().showMessage(f"Saved {path}", 3000)

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    # ==================================================================
    # Validation
    # ==================================================================
    def _schedule_validate(self) -> None:
        self._validate_timer.start()

    def _run_validation(self) -> None:
        issues = validate(self._game)
        self._issues.set_issues(issues)

    # ==================================================================
    # Window title
    # ==================================================================
    def _update_window_title(self) -> None:
        suffix = ""
        if self._path is not None:
            suffix = f" \u2014 {self._path.name}"
        else:
            suffix = " \u2014 Untitled"
        if self._dirty:
            suffix += " *"
        self.setWindowTitle(f"Game Definition Editor{suffix}")

"""Main window: three-pane editor that ties the other widgets together.

Pane layout:
    [ Section list ][ Section editor (centre) ][ Issues panel ]

Menu bar:
    File: New / Open Character / Save / Save As / Open Game Definition
    Render: Render to PDF...

Validation runs on every edit; rendering goes through the existing
render_pdf() function unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..render import render_pdf, resolve_actor_type
from ..validate import validate, split
from .issues_panel import IssuesPanel
from .section_editors import (
    ComplicationsEditor,
    GrowthEditor,
    IdentityEditor,
    MilestonesEditor,
    NotesEditor,
    PrimeSetEditor,
    SessionsEditor,
    StressEditor,
)
from .section_list import SectionList


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cortex Portfolio Editor")
        self.resize(1500, 900)

        # ----- State ---------------------------------------------------
        self._game: dict | None = None
        self._game_path: Path | None = None
        self._character: dict | None = None
        self._character_path: Path | None = None
        self._actor_type: dict | None = None
        self._dirty: bool = False
        self._editor_cache: dict[tuple[str, str], QWidget] = {}

        # Debounced validate so we don't re-validate on every keystroke.
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(150)
        self._validate_timer.timeout.connect(self._run_validation)

        # ----- UI ------------------------------------------------------
        self._build_menu()
        self._build_central()
        self.setStatusBar(QStatusBar())
        self._update_window_title()
        self._update_status()

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")

        act_open_game = QAction("Open &Game Definition\u2026", self)
        act_open_game.triggered.connect(self._on_open_game)
        file_menu.addAction(act_open_game)

        act_open_char = QAction("&Open Character\u2026", self)
        act_open_char.setShortcut(QKeySequence.StandardKey.Open)
        act_open_char.triggered.connect(self._on_open_character)
        file_menu.addAction(act_open_char)

        file_menu.addSeparator()

        act_new = QAction("&New Character", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._on_new_character)
        file_menu.addAction(act_new)

        file_menu.addSeparator()

        act_save = QAction("&Save", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._on_save)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save &As\u2026", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(act_save_as)

        # ----- Game Definition menu (opens its own window) -----
        gd_menu = bar.addMenu("&Game Definition")

        act_gd_new = QAction("&New Game Definition\u2026", self)
        act_gd_new.triggered.connect(lambda: self._open_gd_window(action="new"))
        gd_menu.addAction(act_gd_new)

        act_gd_open = QAction("&Open Game Definition for Editing\u2026", self)
        act_gd_open.triggered.connect(lambda: self._open_gd_window(action="open"))
        gd_menu.addAction(act_gd_open)

        # ----- Render menu -----
        render_menu = bar.addMenu("&Render")
        act_render = QAction("Render to &PDF\u2026", self)
        act_render.setShortcut(QKeySequence("Ctrl+R"))
        act_render.triggered.connect(self._on_render)
        render_menu.addAction(act_render)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ----- left pane: section list -------------------------------
        self._section_list = SectionList()
        self._section_list.sectionSelected.connect(self._on_section_selected)
        splitter.addWidget(self._section_list)

        # ----- centre pane: stacked editors --------------------------
        self._stack = QStackedWidget()
        # The placeholder shown when nothing is loaded yet.
        placeholder = QLabel(
            "Open a character file to start editing.\n\n"
            "File \u203a Open Character\u2026 (or File \u203a Open Game Definition first, "
            "then File \u203a New Character)."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #777; padding: 40px;")
        self._stack.addWidget(placeholder)
        splitter.addWidget(self._stack)

        # ----- right pane: issues ------------------------------------
        self._issues = IssuesPanel()
        self._issues.issueClicked.connect(self._on_issue_clicked)
        splitter.addWidget(self._issues)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 900, 380])
        self.setCentralWidget(splitter)

    # ==================================================================
    # Game-definition editor (opens in its own window)
    # ==================================================================
    def _open_gd_window(self, *, action: str = "new") -> None:
        from .game_def_window import GameDefWindow
        # Keep a reference so the window isn't GC'd. A fresh window each time
        # is fine for now; users can close them when done.
        if not hasattr(self, "_gd_windows"):
            self._gd_windows: list[GameDefWindow] = []
        win = GameDefWindow()
        self._gd_windows.append(win)
        win.show()
        if action == "open":
            # Trigger the open dialog after the window is up.
            QTimer.singleShot(0, win._on_open)

    # ==================================================================
    # File operations
    # ==================================================================
    def _on_open_game(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Game Definition", "", "JSON files (*.json)"
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            game = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Open failed", f"Could not load:\n{e}")
            return
        self._game = game
        self._game_path = path
        self._update_status()
        # If a character is already loaded, re-resolve.
        if self._character is not None:
            self._reset_actor_type_from_character()

    def _on_open_character(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Character", "", "JSON files (*.json)"
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            character = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Open failed", f"Could not load:\n{e}")
            return
        if self._game is None:
            # Helpful: ask for the matching game definition.
            QMessageBox.information(
                self,
                "Game definition needed",
                "Please select the game definition this character was built against.",
            )
            self._on_open_game()
            if self._game is None:
                return
        self._character = character
        self._character_path = path
        self._dirty = False
        self._reset_actor_type_from_character()

    def _on_new_character(self) -> None:
        if self._game is None:
            QMessageBox.information(
                self,
                "Game definition needed",
                "Open a game definition first (File \u203a Open Game Definition).",
            )
            return
        # Pick the first declared actor_type.
        actor_types = self._game.get("actor_types") or {}
        first_id = next(iter(actor_types), None)
        if first_id is None:
            QMessageBox.warning(
                self, "Empty game definition",
                "This game definition has no actor types declared.",
            )
            return
        self._character = {
            "game_definition": self._game.get("id", ""),
            "actor_type": first_id,
            "identity": {},
            "prime_sets": {},
            "extras": {},
        }
        self._character_path = None
        self._dirty = True
        self._reset_actor_type_from_character()

    def _on_save(self) -> None:
        if self._character is None:
            return
        if self._character_path is None:
            self._on_save_as()
            return
        self._write_character(self._character_path)

    def _on_save_as(self) -> None:
        if self._character is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Character As", "", "JSON files (*.json)"
        )
        if not path_str:
            return
        self._write_character(Path(path_str))

    def _write_character(self, path: Path) -> None:
        try:
            path.write_text(
                json.dumps(self._character, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            QMessageBox.critical(self, "Save failed", f"Could not save:\n{e}")
            return
        self._character_path = path
        self._dirty = False
        self._update_window_title()
        self.statusBar().showMessage(f"Saved {path}", 3000)

    # ==================================================================
    # Render
    # ==================================================================
    def _on_render(self) -> None:
        if self._game_path is None or self._character is None:
            QMessageBox.warning(self, "Nothing to render", "Load a character first.")
            return

        # Validation gate -- block on errors only (warnings get rendered
        # gracefully by the existing renderer).
        issues = validate(self._game, self._character)
        errs, _ = split(issues)
        if errs:
            QMessageBox.warning(
                self, "Validation errors",
                f"Cannot render with {len(errs)} error(s) outstanding. "
                f"See the Issues panel.",
            )
            return

        # If unsaved, save to a temp file so render_pdf has a real path.
        if self._character_path is None or self._dirty:
            reply = QMessageBox.question(
                self, "Save first?",
                "The character must be saved before rendering. Save now?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Save:
                return
            self._on_save()
            if self._dirty:  # save failed or was cancelled
                return

        suggested = ""
        if self._character_path is not None:
            suggested = str(self._character_path.with_suffix(".pdf"))
        out_str, _ = QFileDialog.getSaveFileName(
            self, "Render to PDF", suggested, "PDF (*.pdf)"
        )
        if not out_str:
            return
        out_path = Path(out_str)
        try:
            assert self._game_path and self._character_path
            render_pdf(self._game_path, self._character_path, out_path)
        except Exception as e:
            QMessageBox.critical(self, "Render failed", str(e))
            return
        self.statusBar().showMessage(f"Rendered {out_path}", 4000)

    # ==================================================================
    # Internal: routing edits, validation, section switching
    # ==================================================================
    def _reset_actor_type_from_character(self) -> None:
        if self._game is None or self._character is None:
            return
        try:
            self._actor_type = resolve_actor_type(self._game, self._character.get("actor_type"))
        except ValueError as e:
            QMessageBox.warning(self, "Unknown actor type", str(e))
            self._actor_type = None

        self._editor_cache.clear()
        self._section_list.populate(self._actor_type or {}, self._character or {})
        # Explicit selection of Identity to populate the centre pane.
        self._section_list.select("identity")
        self._update_window_title()
        self._update_status()
        self._schedule_validate()

    def _on_section_selected(self, kind: str, id_: str) -> None:
        if self._character is None or self._actor_type is None:
            return
        editor = self._get_or_make_editor(kind, id_)
        if editor is None:
            return
        # Push the latest character data into the editor before showing.
        if hasattr(editor, "set_character"):
            editor.set_character(self._character)
        idx = self._stack.indexOf(editor)
        if idx < 0:
            idx = self._stack.addWidget(editor)
        self._stack.setCurrentIndex(idx)

    def _get_or_make_editor(self, kind: str, id_: str) -> QWidget | None:
        key = (kind, id_)
        if key in self._editor_cache:
            return self._editor_cache[key]

        editor: QWidget | None = None
        if kind == "identity":
            editor = IdentityEditor()
        elif kind == "prime_set":
            ps_def = next(
                (ps for ps in (self._actor_type or {}).get("prime_sets", []) if ps.get("id") == id_),
                None,
            )
            if ps_def is None:
                return None
            editor = PrimeSetEditor(ps_def)
        elif kind == "stress":
            stress_def = ((self._actor_type or {}).get("extras") or {}).get("stress") or {}
            editor = StressEditor(stress_def)
        elif kind == "milestones":
            editor = MilestonesEditor()
        elif kind == "growth":
            editor = GrowthEditor()
        elif kind == "sessions":
            editor = SessionsEditor()
        elif kind == "complications":
            editor = ComplicationsEditor()
        elif kind == "notes":
            editor = NotesEditor()
        else:
            return None

        editor.dataChanged.connect(self._on_data_changed)
        self._editor_cache[key] = editor
        return editor

    def _on_data_changed(self, character: dict) -> None:
        self._character = character
        self._dirty = True
        self._update_window_title()

        # IMPORTANT: do NOT rebuild the section list here. populate() calls
        # clear() + setCurrentRow(0), which steals focus from whatever input
        # the user is typing into. That made QLineEdit "bounce" the cursor
        # out (and QPlainTextEdit type backwards because the cursor was
        # reset to position 0 between keystrokes). Instead, just refresh
        # the count labels in place.
        self._section_list.update_counts(self._actor_type or {}, character)
        self._schedule_validate()

    def _on_issue_clicked(self, kind: str, id_: str) -> None:
        self._section_list.select(kind, id_)

    # ------------------------------------------------------------------
    def _schedule_validate(self) -> None:
        self._validate_timer.start()

    def _run_validation(self) -> None:
        if self._game is None or self._character is None:
            self._issues.set_issues([])
            return
        issues = validate(self._game, self._character)
        self._issues.set_issues(issues)

    # ------------------------------------------------------------------
    def _update_window_title(self) -> None:
        suffix = ""
        if self._character_path is not None:
            suffix = f" \u2014 {self._character_path.name}"
        elif self._character is not None:
            suffix = " \u2014 Untitled"
        if self._dirty:
            suffix += " *"
        self.setWindowTitle(f"Cortex Portfolio Editor{suffix}")

    def _update_status(self) -> None:
        bits = []
        if self._game is not None:
            bits.append(f"Game: {self._game.get('name', '?')}")
        if self._character is not None:
            bits.append(f"Actor type: {self._character.get('actor_type', '?')}")
        self.statusBar().showMessage("    ".join(bits) if bits else "No character loaded")

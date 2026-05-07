"""Centre-pane section editors.

Each section kind gets a dedicated editor:
  - PrimeSetEditor: list of traits with add/remove + a TraitForm per trait
  - IdentityEditor: name/callsign/concept/player free-text
  - StressEditor:   per-track stress + trauma die selector
  - MilestonesEditor: list of named milestones with tier text
  - NotesEditor:    plain text notes

Every editor exposes `dataChanged(dict)` -- a signal carrying the entire
character with the latest edit applied. The main window listens to this
to drive auto-save state, validation, and re-rendering.
"""
from __future__ import annotations

import copy
from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import VALID_DICE
from .trait_form import TraitForm


def _scroll_wrap(inner: QWidget) -> QScrollArea:
    """Wrap a widget so vertical overflow scrolls instead of clipping."""
    scroll = QScrollArea()
    scroll.setWidget(inner)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    return scroll


# ===========================================================================
# Identity
# ===========================================================================

class IdentityEditor(QWidget):
    dataChanged = pyqtSignal(dict)

    _FIELDS = [
        ("name",     "Name"),
        ("callsign", "Callsign"),
        ("concept",  "Concept"),
        ("player",   "Player"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._character: dict = {}
        self._inputs: dict[str, QLineEdit] = {}

        form = QFormLayout(self)
        for key, label in self._FIELDS:
            edit = QLineEdit()
            edit.textChanged.connect(lambda val, k=key: self._set(k, val))
            form.addRow(QLabel(label), edit)
            self._inputs[key] = edit

    def set_character(self, character: dict) -> None:
        self._character = character
        ident = character.get("identity") or {}
        for key, edit in self._inputs.items():
            edit.blockSignals(True)
            edit.setText(ident.get(key, ""))
            edit.blockSignals(False)

    def _set(self, key: str, val: str) -> None:
        ident = self._character.setdefault("identity", {})
        if val:
            ident[key] = val
        else:
            ident.pop(key, None)
        self.dataChanged.emit(self._character)


# ===========================================================================
# Prime Set
# ===========================================================================

class PrimeSetEditor(QWidget):
    """Edit all traits within a single prime set.

    Layout: a header (label + count + 'Add' button), then one TraitForm-in-
    a-frame per trait. Each frame has up/down/remove controls. New traits
    seed sensibly from the prime-set's default_dice / items.
    """
    dataChanged = pyqtSignal(dict)

    def __init__(self, ps_def: dict, parent=None) -> None:
        super().__init__(parent)
        self._ps_def = ps_def
        self._character: dict = {}
        self._ps_id: str = ps_def.get("id", "")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ----- header --------------------------------------------------
        header = QHBoxLayout()
        title = QLabel(f"<h3>{ps_def.get('label', self._ps_id)}</h3>")
        header.addWidget(title)
        header.addStretch(1)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #666;")
        header.addWidget(self._count_label)

        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._on_add)
        header.addWidget(add_btn)
        outer.addLayout(header)

        # ----- traits container ---------------------------------------
        self._traits_inner = QWidget()
        self._traits_layout = QVBoxLayout(self._traits_inner)
        self._traits_layout.setContentsMargins(0, 0, 0, 0)
        self._traits_layout.setSpacing(8)
        self._traits_layout.addStretch(1)
        outer.addWidget(_scroll_wrap(self._traits_inner), 1)

        self._frames: list[QFrame] = []

    # ------------------------------------------------------------------
    def set_character(self, character: dict) -> None:
        self._character = character
        self._rebuild()

    # ------------------------------------------------------------------
    def _entries(self) -> list[dict]:
        return self._character.setdefault("prime_sets", {}).setdefault(self._ps_id, [])

    def _update_count_label(self) -> None:
        count = len(self._entries())
        cmin = (self._ps_def.get("count") or {}).get("min")
        cmax = (self._ps_def.get("count") or {}).get("max")
        text = f"{count} entries"
        if cmin is not None or cmax is not None:
            constraint = f"{cmin or 0}\u2013{cmax if cmax is not None else '\u221e'}"
            text = f"{count}    (allowed: {constraint})"
        self._count_label.setText(text)

    def _rebuild(self) -> None:
        # Drop existing frames
        for f in self._frames:
            f.deleteLater()
        self._frames = []

        # Insert traits before the trailing stretch
        entries = self._entries()
        for i, _entry in enumerate(entries):
            frame = self._make_trait_frame(i)
            self._frames.append(frame)
            self._traits_layout.insertWidget(self._traits_layout.count() - 1, frame)

        self._update_count_label()

    def _make_trait_frame(self, index: int) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        v = QVBoxLayout(frame)
        v.setContentsMargins(6, 6, 6, 6)

        # Trait controls strip
        ctrl = QHBoxLayout()
        ctrl.addStretch(1)
        up = QPushButton("\u2191"); up.setFixedWidth(24); up.setToolTip("Move up")
        dn = QPushButton("\u2193"); dn.setFixedWidth(24); dn.setToolTip("Move down")
        rm = QPushButton("\u2715"); rm.setFixedWidth(24); rm.setToolTip("Remove")
        up.clicked.connect(lambda _, i=index: self._move(i, -1))
        dn.clicked.connect(lambda _, i=index: self._move(i, +1))
        rm.clicked.connect(lambda _, i=index: self._remove(i))
        for b in (up, dn, rm):
            ctrl.addWidget(b)
        v.addLayout(ctrl)

        form = TraitForm(self._ps_def)
        form.set_trait(self._entries()[index])
        form.traitChanged.connect(lambda trait, i=index: self._update_trait(i, trait))
        v.addWidget(form)
        return frame

    def _seed_new_trait(self) -> dict:
        """Build a fresh trait shaped to fit the prime set's settings."""
        s = self._ps_def.get("settings") or {}
        new: dict = {}
        if s.get("has_label", True):
            items = self._ps_def.get("items")
            if isinstance(items, list) and items:
                # Pick the first item not already present
                taken = {e.get("name") for e in self._entries()}
                for it in items:
                    if it.get("name") not in taken:
                        new["name"] = it["name"]
                        break
                else:
                    new["name"] = items[0]["name"]
            else:
                new["name"] = ""
        if s.get("has_dice", True):
            default = self._ps_def.get("default_dice") or self._ps_def.get("dice") or ["d6"]
            new["dice"] = [default[0]] if default else ["d6"]
        return new

    # ------------------------------------------------------------------
    def _on_add(self) -> None:
        self._entries().append(self._seed_new_trait())
        self._rebuild()
        self.dataChanged.emit(self._character)

    def _remove(self, index: int) -> None:
        entries = self._entries()
        if 0 <= index < len(entries):
            del entries[index]
            self._rebuild()
            self.dataChanged.emit(self._character)

    def _move(self, index: int, delta: int) -> None:
        entries = self._entries()
        new_index = index + delta
        if not (0 <= new_index < len(entries)):
            return
        entries[index], entries[new_index] = entries[new_index], entries[index]
        self._rebuild()
        self.dataChanged.emit(self._character)

    def _update_trait(self, index: int, trait: dict) -> None:
        entries = self._entries()
        if 0 <= index < len(entries):
            entries[index] = trait
            self.dataChanged.emit(self._character)


# ===========================================================================
# Stress
# ===========================================================================

class StressEditor(QWidget):
    dataChanged = pyqtSignal(dict)

    def __init__(self, stress_def: dict, parent=None) -> None:
        super().__init__(parent)
        self._stress_def = stress_def
        self._character: dict = {}
        self._stress_widgets: dict[str, QComboBox] = {}
        self._trauma_widgets: dict[str, QComboBox] = {}

        outer = QVBoxLayout(self)
        outer.addWidget(QLabel("<h3>Stress &amp; Trauma</h3>"))

        form = QFormLayout()
        trauma_enabled = stress_def.get("trauma_enabled", False)
        die_options = ["\u2014"] + [d for d in ("d4", "d6", "d8", "d10", "d12")]

        for track in stress_def.get("tracks") or []:
            tid = track.get("id", "")
            label = track.get("label", tid)

            row = QHBoxLayout()
            stress_combo = QComboBox()
            stress_combo.addItems(die_options)
            stress_combo.currentTextChanged.connect(
                lambda val, t=tid: self._set_track("stress", t, val)
            )
            self._stress_widgets[tid] = stress_combo
            row.addWidget(stress_combo)

            if trauma_enabled:
                row.addSpacing(16)
                row.addWidget(QLabel("Trauma:"))
                trauma_combo = QComboBox()
                trauma_combo.addItems(die_options)
                trauma_combo.currentTextChanged.connect(
                    lambda val, t=tid: self._set_track("trauma", t, val)
                )
                self._trauma_widgets[tid] = trauma_combo
                row.addWidget(trauma_combo)

            row.addStretch(1)
            wrap = QWidget(); wrap.setLayout(row)
            form.addRow(QLabel(label), wrap)

        outer.addLayout(form)
        outer.addStretch(1)

    def set_character(self, character: dict) -> None:
        self._character = character
        char_extras = character.setdefault("extras", {})
        for kind, widgets in (("stress", self._stress_widgets),
                              ("trauma", self._trauma_widgets)):
            data = char_extras.get(kind) or {}
            for tid, combo in widgets.items():
                combo.blockSignals(True)
                val = data.get(tid)
                if val is None or val not in VALID_DICE:
                    combo.setCurrentIndex(0)
                else:
                    idx = combo.findText(val)
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                combo.blockSignals(False)

    def _set_track(self, kind: str, track_id: str, val: str) -> None:
        bag = self._character.setdefault("extras", {}).setdefault(kind, {})
        if val == "\u2014" or not val:
            bag[track_id] = None
        else:
            bag[track_id] = val
        self.dataChanged.emit(self._character)


# ===========================================================================
# Milestones
# ===========================================================================

class MilestonesEditor(QWidget):
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._character: dict = {}

        outer = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("<h3>Milestones</h3>"))
        head.addStretch(1)
        add = QPushButton("+ Add Milestone")
        add.clicked.connect(self._on_add)
        head.addWidget(add)
        outer.addLayout(head)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.addStretch(1)
        outer.addWidget(_scroll_wrap(self._inner), 1)

        self._frames: list[QFrame] = []

    def set_character(self, character: dict) -> None:
        self._character = character
        self._rebuild()

    def _milestones(self) -> list[dict]:
        return self._character.setdefault("extras", {}).setdefault("milestones", [])

    def _rebuild(self) -> None:
        for f in self._frames:
            f.deleteLater()
        self._frames = []

        for i, m in enumerate(self._milestones()):
            frame = self._make_milestone_frame(i, m)
            self._frames.append(frame)
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, frame)

    def _make_milestone_frame(self, index: int, m: dict) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        v = QVBoxLayout(frame)

        # Name + remove
        head = QHBoxLayout()
        name = QLineEdit(m.get("name", ""))
        name.setPlaceholderText("Milestone name")
        name.textChanged.connect(lambda val, i=index: self._update(i, "name", val))
        head.addWidget(name, 1)
        rm = QPushButton("\u2715"); rm.setFixedWidth(24); rm.setToolTip("Remove")
        rm.clicked.connect(lambda _, i=index: self._remove(i))
        head.addWidget(rm)
        v.addLayout(head)

        # Tiers (default to 1XP / 3XP / 10XP)
        tiers_box = QGroupBox("Tiers")
        tiers_form = QFormLayout(tiers_box)
        tiers = m.get("tiers") or {"1 XP": "", "3 XP": "", "10 XP": ""}
        for key in ("1 XP", "3 XP", "10 XP"):
            edit = QLineEdit(tiers.get(key, ""))
            edit.setPlaceholderText(f"What earns this character {key}?")
            edit.textChanged.connect(
                lambda val, i=index, k=key: self._update_tier(i, k, val)
            )
            tiers_form.addRow(QLabel(key), edit)
        v.addWidget(tiers_box)
        return frame

    def _on_add(self) -> None:
        self._milestones().append({
            "name": "",
            "tiers": {"1 XP": "", "3 XP": "", "10 XP": ""},
        })
        self._rebuild()
        self.dataChanged.emit(self._character)

    def _remove(self, index: int) -> None:
        ms = self._milestones()
        if 0 <= index < len(ms):
            del ms[index]
            self._rebuild()
            self.dataChanged.emit(self._character)

    def _update(self, index: int, field: str, val: str) -> None:
        ms = self._milestones()
        if 0 <= index < len(ms):
            ms[index][field] = val
            self.dataChanged.emit(self._character)

    def _update_tier(self, index: int, key: str, val: str) -> None:
        ms = self._milestones()
        if 0 <= index < len(ms):
            ms[index].setdefault("tiers", {})[key] = val
            self.dataChanged.emit(self._character)


# ===========================================================================
# Notes
# ===========================================================================

class NotesEditor(QWidget):
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._character: dict = {}

        v = QVBoxLayout(self)
        v.addWidget(QLabel("<h3>Notes</h3>"))

        # Plot points lives at the top of notes for now -- it's the only
        # other extras field that doesn't have its own section.
        pp_row = QHBoxLayout()
        pp_row.addWidget(QLabel("Plot Points"))
        self._pp = QSpinBox()
        self._pp.setRange(0, 99)
        self._pp.valueChanged.connect(self._on_pp_change)
        pp_row.addWidget(self._pp)
        pp_row.addStretch(1)
        v.addLayout(pp_row)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Free-text notes about this character\u2026")
        self._notes.textChanged.connect(self._on_notes_change)
        v.addWidget(self._notes, 1)

    def set_character(self, character: dict) -> None:
        self._character = character
        self._notes.blockSignals(True)
        self._notes.setPlainText(character.get("notes", ""))
        self._notes.blockSignals(False)

        self._pp.blockSignals(True)
        pp_val = character.get("extras", {}).get("plot_points")
        self._pp.setValue(pp_val if isinstance(pp_val, int) else 0)
        self._pp.blockSignals(False)

    def _on_notes_change(self) -> None:
        text = self._notes.toPlainText()
        if text:
            self._character["notes"] = text
        else:
            self._character.pop("notes", None)
        self.dataChanged.emit(self._character)

    def _on_pp_change(self, value: int) -> None:
        self._character.setdefault("extras", {})["plot_points"] = value
        self.dataChanged.emit(self._character)

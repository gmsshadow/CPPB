"""Flag-driven trait editor.

A single widget that, given a prime-set *definition* (with its `settings`
capability flags) and a *trait* dict, builds the appropriate input controls
and emits `traitChanged` whenever the user edits anything.

This is the editor's most important widget: every prime-set variant -- from
plain Attributes to Skills-with-Specialties to Power-Sets-with-Powers-and-
SFX-and-Limits -- routes through this same code path. The settings flags
that drive the renderer drive the editor too.

External callers should:
  1. Construct a TraitForm(prime_set_def).
  2. Call form.set_trait(trait_dict).
  3. Connect to form.traitChanged to receive updated trait dicts.
"""
from __future__ import annotations

import copy
from typing import Any

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
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import VALID_DICE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allowed_dice_for(ps_def: dict) -> list[str]:
    """Resolve the dice pool a trait may use from the prime-set definition."""
    pool = ps_def.get("dice") or ps_def.get("default_dice") or sorted(VALID_DICE)
    # Preserve definition order (d4 < d6 < d8 ...) for natural-feeling pickers.
    return [d for d in pool if d in VALID_DICE]


def _allowed_subtrait_dice(ps_def: dict) -> list[str]:
    settings = ps_def.get("settings") or {}
    pool = settings.get("sub_traits_dice") or _allowed_dice_for(ps_def)
    return [d for d in pool if d in VALID_DICE]


# ---------------------------------------------------------------------------
# Reusable atomic editors
# ---------------------------------------------------------------------------

class DiceRow(QWidget):
    """Editor for a list of dice (`["d8"]` or `["d6", "d6"]`).

    Shows one combo per die plus a + button to add another. Empty pool means
    the trait has no dice (e.g. a Power Set heading itself).
    """

    diceChanged = pyqtSignal(list)  # emits the new list of die strings

    def __init__(self, allowed: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._allowed = allowed
        self._dice: list[str] = []

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(4)

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedWidth(24)
        self._add_btn.setToolTip("Add a die")
        self._add_btn.clicked.connect(self._on_add_clicked)

        self._rebuild()

    # ----- public API ---------------------------------------------------
    def set_dice(self, dice: list[str]) -> None:
        self._dice = list(dice or [])
        self._rebuild()

    def dice(self) -> list[str]:
        return list(self._dice)

    # ----- internals ----------------------------------------------------
    def _rebuild(self) -> None:
        # Drop everything from the row layout, then re-emit the controls
        # based on current state. Simpler than diffing.
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._add_btn:
                w.deleteLater()

        for i, d in enumerate(self._dice):
            self._row.addWidget(self._make_die_combo(i, d))

        self._row.addWidget(self._add_btn)
        self._row.addStretch(1)

    def _make_die_combo(self, index: int, current: str) -> QWidget:
        """Build a (combo, remove-button) widget pair wrapped in a container."""
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)

        combo = QComboBox()
        combo.addItems(self._allowed)
        if current in self._allowed:
            combo.setCurrentIndex(self._allowed.index(current))
        elif current:
            combo.addItem(current)
            combo.setCurrentIndex(combo.count() - 1)
        combo.currentTextChanged.connect(lambda val, i=index: self._on_change(i, val))
        h.addWidget(combo)

        rm = QPushButton("\u2715")
        rm.setFixedWidth(20)
        rm.setToolTip("Remove this die")
        rm.clicked.connect(lambda _checked, i=index: self._on_remove(i))
        h.addWidget(rm)

        return wrap

    def _on_add_clicked(self) -> None:
        # Default new die: first allowed value, or d6 if pool is empty.
        new_die = self._allowed[0] if self._allowed else "d6"
        self._dice.append(new_die)
        self._rebuild()
        self.diceChanged.emit(list(self._dice))

    def _on_change(self, index: int, val: str) -> None:
        if 0 <= index < len(self._dice):
            self._dice[index] = val
            self.diceChanged.emit(list(self._dice))

    def _on_remove(self, index: int) -> None:
        if len(self._dice) <= 0:
            return
        if 0 <= index < len(self._dice):
            del self._dice[index]
            self._rebuild()
            self.diceChanged.emit(list(self._dice))


class NamedItemsEditor(QWidget):
    """Editor for a list of `{name, text}` items (used by SFX and Limits).

    Shows each item as a name input + multi-line text input + remove button.
    A row of "+ Add" appears at the bottom.
    """

    itemsChanged = pyqtSignal(list)

    def __init__(self, label_singular: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label_singular
        self._items: list[dict] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

        self._add_btn = QPushButton(f"+ Add {label_singular}")
        self._add_btn.clicked.connect(self._on_add)

        self._rebuild()

    def set_items(self, items: list[dict]) -> None:
        self._items = [dict(it) for it in (items or [])]
        self._rebuild()

    def items(self) -> list[dict]:
        return [dict(it) for it in self._items]

    def _rebuild(self) -> None:
        # Take everything out of the layout, but only delete the dynamic
        # item widgets -- the persistent _add_btn must be preserved across
        # rebuilds (deleteLater on it would invalidate it for next time).
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._add_btn:
                w.deleteLater()

        for i, item in enumerate(self._items):
            self._layout.addWidget(self._make_item_widget(i, item))

        self._layout.addWidget(self._add_btn)

    def _make_item_widget(self, index: int, item: dict) -> QWidget:
        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        head = QHBoxLayout()
        name_edit = QLineEdit(item.get("name", ""))
        name_edit.setPlaceholderText(f"{self._label} name")
        name_edit.textChanged.connect(
            lambda val, i=index: self._update_field(i, "name", val)
        )
        head.addWidget(name_edit, 1)

        rm_btn = QPushButton("\u2715")  # ✕
        rm_btn.setFixedWidth(24)
        rm_btn.setToolTip(f"Remove this {self._label.lower()}")
        rm_btn.clicked.connect(lambda _checked, i=index: self._on_remove(i))
        head.addWidget(rm_btn)

        v.addLayout(head)

        text_edit = QTextEdit(item.get("text", ""))
        text_edit.setPlaceholderText(f"{self._label} text")
        text_edit.setFixedHeight(54)
        text_edit.textChanged.connect(
            lambda i=index, te=text_edit: self._update_field(i, "text", te.toPlainText())
        )
        v.addWidget(text_edit)
        return box

    def _on_add(self) -> None:
        self._items.append({"name": "", "text": ""})
        self._rebuild()
        self.itemsChanged.emit(self.items())

    def _on_remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self._rebuild()
            self.itemsChanged.emit(self.items())

    def _update_field(self, index: int, field: str, value: str) -> None:
        if 0 <= index < len(self._items):
            self._items[index][field] = value
            self.itemsChanged.emit(self.items())


class SubTraitsEditor(QWidget):
    """Editor for a list of sub-traits (Specialties, Powers, etc.).

    Each sub-trait has a name and (optionally) a list of dice.
    """

    subTraitsChanged = pyqtSignal(list)

    def __init__(
        self,
        ps_def: dict,
        label_singular: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        settings = ps_def.get("settings") or {}
        self._label = label_singular
        self._allowed_dice = _allowed_subtrait_dice(ps_def)
        self._have_dice = settings.get("sub_traits_have_dice", True)
        self._items: list[dict] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)

        self._add_btn = QPushButton(f"+ Add {label_singular}")
        self._add_btn.clicked.connect(self._on_add)
        self._rebuild()

    def set_sub_traits(self, items: list[dict]) -> None:
        self._items = [copy.deepcopy(it) for it in (items or [])]
        self._rebuild()

    def sub_traits(self) -> list[dict]:
        return [copy.deepcopy(it) for it in self._items]

    def _rebuild(self) -> None:
        # Preserve the persistent add button across rebuilds.
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._add_btn:
                w.deleteLater()

        for i, item in enumerate(self._items):
            self._layout.addWidget(self._make_sub_widget(i, item))
        self._layout.addWidget(self._add_btn)

    def _make_sub_widget(self, index: int, item: dict) -> QWidget:
        box = QFrame()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        name = QLineEdit(item.get("name", ""))
        name.setPlaceholderText(f"{self._label} name")
        name.textChanged.connect(
            lambda val, i=index: self._update_field(i, "name", val)
        )
        h.addWidget(name, 1)

        if self._have_dice:
            dice_row = DiceRow(self._allowed_dice)
            dice_row.set_dice(item.get("dice") or [])
            dice_row.diceChanged.connect(
                lambda val, i=index: self._update_field(i, "dice", val)
            )
            h.addWidget(dice_row)

        rm_btn = QPushButton("\u2715")
        rm_btn.setFixedWidth(24)
        rm_btn.setToolTip(f"Remove this {self._label.lower()}")
        rm_btn.clicked.connect(lambda _checked, i=index: self._on_remove(i))
        h.addWidget(rm_btn)

        return box

    def _on_add(self) -> None:
        new_item: dict = {"name": ""}
        if self._have_dice:
            new_item["dice"] = [self._allowed_dice[0]] if self._allowed_dice else ["d6"]
        self._items.append(new_item)
        self._rebuild()
        self.subTraitsChanged.emit(self.sub_traits())

    def _on_remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self._rebuild()
            self.subTraitsChanged.emit(self.sub_traits())

    def _update_field(self, index: int, field: str, value: Any) -> None:
        if 0 <= index < len(self._items):
            self._items[index][field] = value
            self.subTraitsChanged.emit(self.sub_traits())


# ---------------------------------------------------------------------------
# The main TraitForm
# ---------------------------------------------------------------------------

class TraitForm(QWidget):
    """Single-trait editor whose visible fields are driven by capability flags.

    Reads `ps_def["settings"]` to decide what to show:
      has_label         -> name field
      has_dice          -> dice picker
      has_description   -> description text area
      has_statement     -> statement text area
      has_sub_traits    -> sub-traits editor with the configured label
      has_sfx           -> SFX list editor
      has_limits        -> Limits list editor

    Items in `prime_set.items` (predefined attribute/skill/value lists)
    constrain the name field to a dropdown rather than free text.
    """

    traitChanged = pyqtSignal(dict)

    def __init__(self, ps_def: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ps_def = ps_def
        self._settings = ps_def.get("settings") or {}
        self._trait: dict = {}
        self._suspend_signals = False

        self._build_ui()

    # -------- public API -----------------------------------------------
    def set_trait(self, trait: dict) -> None:
        """Load a trait into the form. Does not emit traitChanged."""
        self._trait = copy.deepcopy(trait or {})
        self._suspend_signals = True
        try:
            self._populate()
        finally:
            self._suspend_signals = False

    def trait(self) -> dict:
        return copy.deepcopy(self._trait)

    # -------- UI construction ------------------------------------------
    def _build_ui(self) -> None:
        s = self._settings
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        # ----- Name -----
        if s.get("has_label", True):
            items = self._ps_def.get("items")
            if isinstance(items, list) and items:
                self._name_widget = QComboBox()
                names = [it["name"] for it in items if isinstance(it, dict) and "name" in it]
                self._name_widget.addItems(names)
                self._name_widget.currentTextChanged.connect(
                    lambda val: self._set_field("name", val)
                )
            else:
                self._name_widget = QLineEdit()
                self._name_widget.setPlaceholderText("Trait name")
                self._name_widget.textChanged.connect(
                    lambda val: self._set_field("name", val)
                )
            layout.addRow(QLabel("Name"), self._name_widget)
        else:
            self._name_widget = None

        # ----- Dice -----
        if s.get("has_dice", True):
            self._dice_widget = DiceRow(_allowed_dice_for(self._ps_def))
            self._dice_widget.diceChanged.connect(
                lambda val: self._set_field("dice", val)
            )
            layout.addRow(QLabel("Dice"), self._dice_widget)
        else:
            self._dice_widget = None

        # ----- Description -----
        if s.get("has_description"):
            self._desc_widget = QTextEdit()
            self._desc_widget.setPlaceholderText("Description")
            self._desc_widget.setFixedHeight(60)
            self._desc_widget.textChanged.connect(
                lambda: self._set_field("description", self._desc_widget.toPlainText())
            )
            layout.addRow(QLabel("Description"), self._desc_widget)
        else:
            self._desc_widget = None

        # ----- Statement -----
        if s.get("has_statement"):
            self._statement_widget = QLineEdit()
            self._statement_widget.setPlaceholderText("e.g. \"I will not leave a wingman behind.\"")
            self._statement_widget.textChanged.connect(
                lambda val: self._set_field("statement", val)
            )
            layout.addRow(QLabel("Statement"), self._statement_widget)
        else:
            self._statement_widget = None

        # ----- Sub-traits -----
        if s.get("has_sub_traits"):
            sub_label = s.get("sub_traits_label") or "Sub-trait"
            if sub_label.endswith("ies"):
                singular = sub_label[:-3] + "y"        # Specialties -> Specialty
            elif sub_label.endswith("s"):
                singular = sub_label.rstrip("s")        # Powers -> Power
            else:
                singular = sub_label                    # already singular / unknown
            self._sub_widget = SubTraitsEditor(self._ps_def, singular)
            self._sub_widget.subTraitsChanged.connect(
                lambda val: self._set_field("sub_traits", val)
            )
            box = QGroupBox(sub_label)
            box_v = QVBoxLayout(box)
            box_v.setContentsMargins(8, 8, 8, 8)
            box_v.addWidget(self._sub_widget)
            layout.addRow(box)
        else:
            self._sub_widget = None

        # ----- SFX -----
        if s.get("has_sfx"):
            self._sfx_widget = NamedItemsEditor("SFX")
            self._sfx_widget.itemsChanged.connect(
                lambda val: self._set_field("sfx", val)
            )
            box = QGroupBox("SFX")
            box_v = QVBoxLayout(box)
            box_v.setContentsMargins(8, 8, 8, 8)
            box_v.addWidget(self._sfx_widget)
            layout.addRow(box)
        else:
            self._sfx_widget = None

        # ----- Limits -----
        if s.get("has_limits"):
            self._lim_widget = NamedItemsEditor("Limit")
            self._lim_widget.itemsChanged.connect(
                lambda val: self._set_field("limits", val)
            )
            box = QGroupBox("Limits")
            box_v = QVBoxLayout(box)
            box_v.setContentsMargins(8, 8, 8, 8)
            box_v.addWidget(self._lim_widget)
            layout.addRow(box)
        else:
            self._lim_widget = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _populate(self) -> None:
        t = self._trait
        if self._name_widget is not None:
            name = t.get("name", "")
            if isinstance(self._name_widget, QComboBox):
                idx = self._name_widget.findText(name)
                if idx >= 0:
                    self._name_widget.setCurrentIndex(idx)
                else:
                    # Out-of-list name: keep showing it so the user can fix it
                    if name:
                        self._name_widget.addItem(name)
                        self._name_widget.setCurrentText(name)
            else:
                self._name_widget.setText(name)

        if self._dice_widget is not None:
            self._dice_widget.set_dice(t.get("dice") or [])

        if self._desc_widget is not None:
            self._desc_widget.blockSignals(True)
            self._desc_widget.setPlainText(t.get("description", ""))
            self._desc_widget.blockSignals(False)

        if self._statement_widget is not None:
            self._statement_widget.setText(t.get("statement", ""))

        if self._sub_widget is not None:
            self._sub_widget.set_sub_traits(t.get("sub_traits") or [])

        if self._sfx_widget is not None:
            self._sfx_widget.set_items(t.get("sfx") or [])

        if self._lim_widget is not None:
            self._lim_widget.set_items(t.get("limits") or [])

    def _set_field(self, field: str, value: Any) -> None:
        if self._suspend_signals:
            return
        if value in ("", [], None) and field not in ("name",):
            # Drop empty optional fields so the JSON stays clean.
            self._trait.pop(field, None)
        else:
            self._trait[field] = value
        self.traitChanged.emit(copy.deepcopy(self._trait))

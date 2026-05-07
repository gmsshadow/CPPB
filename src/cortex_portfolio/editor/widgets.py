"""Reusable widgets shared between the character editor and the game-def
editor. Anything here is UI-only -- domain logic lives in render/validate.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import VALID_DICE
from ..render import FA_ICONS


def _ordered_dice() -> list[str]:
    """d4, d6, d8, d10, d12 -- ordered numerically, not lexicographically."""
    return sorted(VALID_DICE, key=lambda d: int(d[1:]))


# ---------------------------------------------------------------------------
# DicePoolEditor: checkbox group representing a SET of allowed dice.
# Used wherever the schema wants a "which dice are valid here" list:
#   - game.dice_pool
#   - prime_set.dice
#   - prime_set.settings.sub_traits_dice
# Distinct from DiceRow (ordered list, e.g. default_dice=["d6", "d6"]).
# ---------------------------------------------------------------------------

class DicePoolEditor(QWidget):
    poolChanged = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all = _ordered_dice()
        self._checks: dict[str, QCheckBox] = {}
        self._suspend = False

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for d in self._all:
            cb = QCheckBox(d)
            cb.toggled.connect(self._emit)
            h.addWidget(cb)
            self._checks[d] = cb
        h.addStretch(1)

    def set_pool(self, pool: list[str] | None) -> None:
        self._suspend = True
        try:
            present = set(pool or [])
            for d, cb in self._checks.items():
                cb.setChecked(d in present)
        finally:
            self._suspend = False

    def pool(self) -> list[str]:
        return [d for d in self._all if self._checks[d].isChecked()]

    def _emit(self) -> None:
        if not self._suspend:
            self.poolChanged.emit(self.pool())


# ---------------------------------------------------------------------------
# IconPicker: combobox over the FA_ICONS keys plus an empty option.
# ---------------------------------------------------------------------------

class IconPicker(QComboBox):
    iconChanged = pyqtSignal(str)  # emits the icon key, or "" for none

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.addItem("(none)", userData="")
        for key in sorted(FA_ICONS.keys()):
            self.addItem(key, userData=key)
        self.currentIndexChanged.connect(self._on_changed)

    def set_icon(self, key: str | None) -> None:
        target = key or ""
        idx = max(0, self.findData(target))
        # blockSignals so calling set_icon() doesn't fire iconChanged
        self.blockSignals(True)
        self.setCurrentIndex(idx)
        self.blockSignals(False)

    def icon_key(self) -> str:
        return self.currentData() or ""

    def _on_changed(self, _idx: int) -> None:
        self.iconChanged.emit(self.icon_key())


# ---------------------------------------------------------------------------
# NameOnlyListEditor: simpler cousin of NamedItemsEditor.
# Stores [{"name": "..."}] items -- used for prime_set.items (predefined
# attribute / skill / value names) where there's no body text to attach.
# ---------------------------------------------------------------------------

class NameOnlyListEditor(QWidget):
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

    def set_items(self, items: list[dict] | None) -> None:
        self._items = [dict(it) for it in (items or [])]
        self._rebuild()

    def items(self) -> list[dict]:
        return [{"name": it.get("name", "")} for it in self._items]

    def _rebuild(self) -> None:
        # Preserve the persistent add button across rebuilds.
        while self._layout.count():
            it = self._layout.takeAt(0)
            w = it.widget()
            if w is not None and w is not self._add_btn:
                w.deleteLater()
        for i, item in enumerate(self._items):
            self._layout.addWidget(self._make_row(i, item))
        self._layout.addWidget(self._add_btn)

    def _make_row(self, index: int, item: dict) -> QWidget:
        wrap = QFrame()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        edit = QLineEdit(item.get("name", ""))
        edit.setPlaceholderText(f"{self._label} name")
        edit.textChanged.connect(lambda val, i=index: self._update(i, val))
        h.addWidget(edit, 1)

        rm = QPushButton("\u2715")
        rm.setFixedWidth(24)
        rm.setToolTip(f"Remove this {self._label.lower()}")
        rm.clicked.connect(lambda _checked, i=index: self._on_remove(i))
        h.addWidget(rm)

        return wrap

    def _on_add(self) -> None:
        self._items.append({"name": ""})
        self._rebuild()
        self.itemsChanged.emit(self.items())

    def _on_remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self._rebuild()
            self.itemsChanged.emit(self.items())

    def _update(self, index: int, value: str) -> None:
        if 0 <= index < len(self._items):
            self._items[index]["name"] = value
            self.itemsChanged.emit(self.items())

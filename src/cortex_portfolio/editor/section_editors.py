"""Centre-pane section editors.

Each section kind gets a dedicated editor:
  - PrimeSetEditor: list of traits with add/remove + a TraitForm per trait
  - IdentityEditor: name/concept/player free-text + optional portrait
  - StressEditor:   per-track stress + trauma die selector
  - MilestonesEditor: list of named milestones with tier text
  - NotesEditor:    plain text notes
  - ComplicationsEditor / GrowthEditor / SessionsEditor: optional list extras

Every editor exposes `dataChanged(dict)` -- a signal carrying the entire
character with the latest edit applied. The main window listens to this
to drive auto-save state, validation, and re-rendering.
"""
from __future__ import annotations

import base64
import copy
import io
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
# Portrait picker
# ===========================================================================

# Portraits get downscaled so they fit inside this box (preserves aspect).
# 600px is plenty -- the rendered PDF only shows the portrait at ~75pt
# square, and we don't want to bloat character JSON files with raw 4MP
# photos. JPEG quality 80 keeps file size around 20-40KB per portrait.
_PORTRAIT_MAX_SIDE = 600
_PORTRAIT_JPEG_QUALITY = 80


def _encode_portrait(path: Path) -> str:
    """Load `path`, downscale, encode as a JPEG data URI string.

    Raises ValueError if the file isn't an image we can decode.
    """
    try:
        img = Image.open(path)
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"Could not read image: {e}") from e

    # Convert anything (RGBA, P, CMYK, ...) to RGB so JPEG encoding is safe.
    # Transparency gets flattened onto white -- portraits rarely need alpha.
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA") or "transparency" in img.info:
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        else:
            img = img.convert("RGB")

    img.thumbnail((_PORTRAIT_MAX_SIDE, _PORTRAIT_MAX_SIDE), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_PORTRAIT_JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


class PortraitPicker(QWidget):
    """A small widget: thumbnail + Choose / Clear buttons.

    The value is a data URI string (or empty). Emits portraitChanged on any
    successful change (load, clear). Decoding errors surface as a QMessageBox
    and don't change state.
    """
    portraitChanged = pyqtSignal(str)

    _THUMB_PX = 96  # editor-side preview size

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data_uri: str = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._thumb = QLabel()
        self._thumb.setFixedSize(self._THUMB_PX, self._THUMB_PX)
        self._thumb.setFrameShape(QFrame.Shape.Box)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            "QLabel { background: #f8f8f8; color: #888; font-size: 9pt; }"
        )
        self._render_thumb()
        layout.addWidget(self._thumb)

        btns = QVBoxLayout()
        btns.setSpacing(4)
        self._choose_btn = QPushButton("Choose Image\u2026")
        self._choose_btn.clicked.connect(self._on_choose)
        btns.addWidget(self._choose_btn)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.setEnabled(False)
        btns.addWidget(self._clear_btn)
        btns.addStretch(1)
        layout.addLayout(btns)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    def set_portrait(self, data_uri: str | None) -> None:
        self._data_uri = data_uri or ""
        self._render_thumb()
        self._clear_btn.setEnabled(bool(self._data_uri))

    def portrait(self) -> str:
        return self._data_uri

    # ------------------------------------------------------------------
    def _render_thumb(self) -> None:
        if not self._data_uri or not self._data_uri.startswith("data:image/"):
            self._thumb.setText("No portrait")
            self._thumb.setPixmap(QPixmap())
            return
        # Decode the data URI back to bytes for preview rendering.
        try:
            _, b64 = self._data_uri.split(",", 1)
            raw = base64.b64decode(b64)
            qimg = QImage.fromData(raw)
            if qimg.isNull():
                raise ValueError("Could not decode embedded image")
            pix = QPixmap.fromImage(qimg).scaled(
                QSize(self._THUMB_PX, self._THUMB_PX),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb.setText("")
            self._thumb.setPixmap(pix)
        except Exception:
            # Stored data is corrupted or unrenderable; show placeholder
            # but don't clear the stored data -- the user can decide.
            self._thumb.setText("(unreadable)")
            self._thumb.setPixmap(QPixmap())

    def _on_choose(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a portrait image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All files (*)",
        )
        if not path_str:
            return
        try:
            data_uri = _encode_portrait(Path(path_str))
        except ValueError as e:
            QMessageBox.warning(self, "Couldn't load image", str(e))
            return
        self.set_portrait(data_uri)
        self.portraitChanged.emit(data_uri)

    def _on_clear(self) -> None:
        self.set_portrait("")
        self.portraitChanged.emit("")


# ===========================================================================
# Identity
# ===========================================================================

class IdentityEditor(QWidget):
    dataChanged = pyqtSignal(dict)

    _FIELDS = [
        ("name",     "Name"),
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

        # Portrait picker. The image data lives in identity.portrait as a
        # JPEG data URI; the picker handles the load/downscale/encode flow.
        self._portrait = PortraitPicker()
        self._portrait.portraitChanged.connect(self._on_portrait_changed)
        form.addRow(QLabel("Portrait"), self._portrait)

    def set_character(self, character: dict) -> None:
        self._character = character
        ident = character.get("identity") or {}
        for key, edit in self._inputs.items():
            edit.blockSignals(True)
            edit.setText(ident.get(key, ""))
            edit.blockSignals(False)
        # Don't emit during populate
        self._portrait.blockSignals(True)
        self._portrait.set_portrait(ident.get("portrait", ""))
        self._portrait.blockSignals(False)

    def _set(self, key: str, val: str) -> None:
        ident = self._character.setdefault("identity", {})
        if val:
            ident[key] = val
        else:
            ident.pop(key, None)
        self.dataChanged.emit(self._character)

    def _on_portrait_changed(self, data_uri: str) -> None:
        ident = self._character.setdefault("identity", {})
        if data_uri:
            ident["portrait"] = data_uri
        else:
            ident.pop("portrait", None)
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
        # other extras field that doesn't have its own section. The value
        # stored here is for between-session record-keeping; the rendered
        # sheet shows a writable box rather than a fixed number, because
        # PP changes too often during play for a printed value to be
        # useful.
        pp_row = QHBoxLayout()
        pp_row.addWidget(QLabel("Plot Points"))
        self._pp = QSpinBox()
        self._pp.setRange(0, 99)
        self._pp.setToolTip(
            "Recorded for reference between sessions. The rendered PDF "
            "shows a writable box instead of this value, since PP changes "
            "constantly during play."
        )
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


# ===========================================================================
# Complications
# ===========================================================================

class ComplicationsEditor(QWidget):
    """Edit the list of complications on a character.

    A complication is just {name, dice} -- a step-rated trait the character
    has picked up during play. Add / remove / edit, with no sub-traits or
    SFX (those would be a Power Set, not a complication).
    """
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._character: dict = {}

        outer = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("<h3>Complications</h3>"))
        head.addStretch(1)
        add = QPushButton("+ Add Complication")
        add.clicked.connect(self._on_add)
        head.addWidget(add)
        outer.addLayout(head)

        info = QLabel(
            "Step-rated traits the character has picked up during play "
            "(\"On Fire d8\", \"Outnumbered d6\"). The PDF reserves printable "
            "blank space if the list is empty, so players can record extras "
            "with pen and paper."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 4px 0 8px 0;")
        outer.addWidget(info)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.addStretch(1)
        outer.addWidget(_scroll_wrap(self._inner), 1)

        self._frames: list[QFrame] = []

    def set_character(self, character: dict) -> None:
        self._character = character
        self._rebuild()

    def _list(self) -> list[dict]:
        return self._character.setdefault("extras", {}).setdefault("complications", [])

    def _rebuild(self) -> None:
        for f in self._frames:
            f.deleteLater()
        self._frames = []
        for i, _c in enumerate(self._list()):
            frame = self._make_row(i)
            self._frames.append(frame)
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, frame)

    def _make_row(self, index: int) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        h = QHBoxLayout(frame)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        c = self._list()[index]

        name = QLineEdit(c.get("name", ""))
        name.setPlaceholderText("Complication name (e.g. On Fire, Outnumbered)")
        name.textChanged.connect(lambda v, i=index: self._update(i, "name", v))
        h.addWidget(name, 1)

        die = QComboBox()
        die.addItems(["d4", "d6", "d8", "d10", "d12"])
        current = (c.get("dice") or ["d6"])[0] if c.get("dice") else "d6"
        idx = die.findText(current)
        die.setCurrentIndex(idx if idx >= 0 else 1)
        die.currentTextChanged.connect(
            lambda v, i=index: self._update(i, "dice", [v])
        )
        h.addWidget(die)

        rm = QPushButton("\u2715")
        rm.setFixedWidth(24)
        rm.setToolTip("Remove")
        rm.clicked.connect(lambda _c, i=index: self._remove(i))
        h.addWidget(rm)
        return frame

    def _on_add(self) -> None:
        self._list().append({"name": "", "dice": ["d6"]})
        self._rebuild()
        self.dataChanged.emit(self._character)

    def _remove(self, index: int) -> None:
        items = self._list()
        if 0 <= index < len(items):
            del items[index]
            self._rebuild()
            self.dataChanged.emit(self._character)

    def _update(self, index: int, field: str, value) -> None:
        items = self._list()
        if 0 <= index < len(items):
            items[index][field] = value
            self.dataChanged.emit(self._character)


# ===========================================================================
# Growth pool entries
# ===========================================================================

class GrowthEditor(QWidget):
    """Edit a character's Growth Pool entries.

    Each entry is {die, text} -- a die rating and a brief description of
    what was earned for. This is a record-keeping aid, not a mechanism;
    the editor doesn't enforce any "spend X dice to advance Y" maths. The
    Tales of Xadia sheet lays these out in fixed slot patterns
    (3xd4, 3xd6, 3xd8, 3xd10, 2xd12) but our schema is just a free-form
    list -- add as many as you like.
    """
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._character: dict = {}

        outer = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("<h3>Growth</h3>"))
        head.addStretch(1)
        add = QPushButton("+ Add Growth Entry")
        add.clicked.connect(self._on_add)
        head.addWidget(add)
        outer.addLayout(head)

        info = QLabel(
            "Each entry pairs a die rating with a brief note about what was "
            "earned. The PDF reserves printable blank space when the list "
            "is empty so awards can be added in pen-and-paper at the table."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 4px 0 8px 0;")
        outer.addWidget(info)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.addStretch(1)
        outer.addWidget(_scroll_wrap(self._inner), 1)

        self._frames: list[QFrame] = []

    def set_character(self, character: dict) -> None:
        self._character = character
        self._rebuild()

    def _list(self) -> list[dict]:
        return self._character.setdefault("extras", {}).setdefault("growth", [])

    def _rebuild(self) -> None:
        for f in self._frames:
            f.deleteLater()
        self._frames = []
        for i, _g in enumerate(self._list()):
            frame = self._make_row(i)
            self._frames.append(frame)
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, frame)

    def _make_row(self, index: int) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        h = QHBoxLayout(frame)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        g = self._list()[index]

        die = QComboBox()
        die.addItems(["d4", "d6", "d8", "d10", "d12"])
        current = g.get("die") or "d6"
        idx = die.findText(current)
        die.setCurrentIndex(idx if idx >= 0 else 1)
        die.currentTextChanged.connect(
            lambda v, i=index: self._update(i, "die", v)
        )
        h.addWidget(die)

        text = QLineEdit(g.get("text", ""))
        text.setPlaceholderText("What this was earned for")
        text.textChanged.connect(lambda v, i=index: self._update(i, "text", v))
        h.addWidget(text, 1)

        rm = QPushButton("\u2715")
        rm.setFixedWidth(24)
        rm.setToolTip("Remove")
        rm.clicked.connect(lambda _c, i=index: self._remove(i))
        h.addWidget(rm)
        return frame

    def _on_add(self) -> None:
        self._list().append({"die": "d6", "text": ""})
        self._rebuild()
        self.dataChanged.emit(self._character)

    def _remove(self, index: int) -> None:
        items = self._list()
        if 0 <= index < len(items):
            del items[index]
            self._rebuild()
            self.dataChanged.emit(self._character)

    def _update(self, index: int, field: str, value) -> None:
        items = self._list()
        if 0 <= index < len(items):
            items[index][field] = value
            self.dataChanged.emit(self._character)


# ===========================================================================
# Session records
# ===========================================================================

class SessionsEditor(QWidget):
    """Edit a character's session records: a list of {name, note?} entries.

    Same shape as Complications and Growth -- a free-form list with add,
    remove, and inline edit. The PDF reserves blank writing lines if the
    list is empty, so groups can use the section in pen-and-paper play.
    """
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._character: dict = {}

        outer = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("<h3>Session Records</h3>"))
        head.addStretch(1)
        add = QPushButton("+ Add Session")
        add.clicked.connect(self._on_add)
        head.addWidget(add)
        outer.addLayout(head)

        info = QLabel(
            "Per-session log on the sheet. Each entry is a session name "
            "(e.g. \"Session 3\" or \"The Storm Spire\") and an optional "
            "brief note. The PDF reserves printable blank space when the "
            "list is empty."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 4px 0 8px 0;")
        outer.addWidget(info)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.addStretch(1)
        outer.addWidget(_scroll_wrap(self._inner), 1)

        self._frames: list[QFrame] = []

    def set_character(self, character: dict) -> None:
        self._character = character
        self._rebuild()

    def _list(self) -> list[dict]:
        return self._character.setdefault("extras", {}).setdefault("sessions", [])

    def _rebuild(self) -> None:
        for f in self._frames:
            f.deleteLater()
        self._frames = []
        for i, _s in enumerate(self._list()):
            frame = self._make_row(i)
            self._frames.append(frame)
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, frame)

    def _make_row(self, index: int) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        h = QHBoxLayout(frame)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        s = self._list()[index]

        name = QLineEdit(s.get("name", ""))
        name.setPlaceholderText("Session name (e.g. Session 3, The Storm Spire)")
        name.textChanged.connect(lambda v, i=index: self._update(i, "name", v))
        h.addWidget(name, 1)

        note = QLineEdit(s.get("note", ""))
        note.setPlaceholderText("Optional brief note")
        note.textChanged.connect(lambda v, i=index: self._update(i, "note", v))
        h.addWidget(note, 2)

        rm = QPushButton("\u2715")
        rm.setFixedWidth(24)
        rm.setToolTip("Remove")
        rm.clicked.connect(lambda _c, i=index: self._remove(i))
        h.addWidget(rm)
        return frame

    def _on_add(self) -> None:
        self._list().append({"name": "", "note": ""})
        self._rebuild()
        self.dataChanged.emit(self._character)

    def _remove(self, index: int) -> None:
        items = self._list()
        if 0 <= index < len(items):
            del items[index]
            self._rebuild()
            self.dataChanged.emit(self._character)

    def _update(self, index: int, field: str, value) -> None:
        items = self._list()
        if 0 <= index < len(items):
            items[index][field] = value
            self.dataChanged.emit(self._character)

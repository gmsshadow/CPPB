"""Forms for editing pieces of a game definition.

Each form exposes:
  - set_data(d: dict)   -- bind to a dict (held by reference)
  - dataChanged signal  -- fires whenever a field changes

The forms mutate the bound dict IN PLACE. This matters: the window holds
the canonical game definition tree and gives forms references to the same
nested dicts. Edits flow back automatically; no copy-back step. Empty
optional fields are *removed* from the dict so the resulting JSON stays
clean.

The widgets that a form rebuilds (NameOnlyListEditor, StressTracksEditor,
flag-conditional sub-blocks) need their visibility state restored after
each `set_data` call -- that's what `_populate` is for. During populate
we suspend signal emission so loading data doesn't fire dataChanged.
"""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .widgets import DicePoolEditor, IconPicker, NameOnlyListEditor


# ===========================================================================
# Helpers
# ===========================================================================

def _set_or_drop(d: dict, key: str, value: Any) -> None:
    """Set d[key] to value, or remove the key entirely if value is empty.

    "Empty" means: empty string, None, [], {}. Booleans (including False)
    are kept -- has_dice=False is meaningful information, not absence.
    """
    if value is False or isinstance(value, (int, float)) and value == 0:
        # Numeric zero and explicit False are NOT empty.
        d[key] = value
        return
    if value in ("", None, [], {}):
        d.pop(key, None)
    else:
        d[key] = value


def _scroll_form() -> tuple[QWidget, QFormLayout]:
    """Return (container, form_layout). Form-layout-of-choice for our forms."""
    w = QWidget()
    f = QFormLayout(w)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    f.setFormAlignment(Qt.AlignmentFlag.AlignTop)
    return w, f


# ===========================================================================
# GameForm -- top-level metadata (id, name, version, description, dice_pool)
# ===========================================================================

class GameForm(QWidget):
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game: dict | None = None
        self._suspend = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        meta_box = QGroupBox("Game definition")
        form = QFormLayout(meta_box)

        self._id = QLineEdit()
        self._id.setPlaceholderText("snake_case identifier, e.g. hammerheads")
        self._id.textChanged.connect(lambda v: self._set("id", v))
        form.addRow("ID", self._id)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Display name")
        self._name.textChanged.connect(lambda v: self._set("name", v))
        form.addRow("Name", self._name)

        self._version = QLineEdit()
        self._version.setPlaceholderText("e.g. 1.0.0")
        self._version.textChanged.connect(lambda v: self._set("version", v))
        form.addRow("Version", self._version)

        self._description = QPlainTextEdit()
        self._description.setPlaceholderText("Optional one-paragraph description.")
        self._description.setFixedHeight(80)
        self._description.textChanged.connect(
            lambda: self._set("description", self._description.toPlainText())
        )
        form.addRow("Description", self._description)

        self._dice_pool = DicePoolEditor()
        self._dice_pool.poolChanged.connect(lambda v: self._set("dice_pool", v))
        form.addRow("Dice pool", self._dice_pool)

        outer.addWidget(meta_box)
        outer.addStretch(1)

    # ----------------------------------------------------------------
    def set_data(self, game: dict) -> None:
        self._game = game
        self._suspend = True
        try:
            self._id.setText(game.get("id", ""))
            self._name.setText(game.get("name", ""))
            self._version.setText(game.get("version", ""))
            self._description.setPlainText(game.get("description", ""))
            self._dice_pool.set_pool(game.get("dice_pool"))
        finally:
            self._suspend = False

    def _set(self, key: str, value: Any) -> None:
        if self._suspend or self._game is None:
            return
        _set_or_drop(self._game, key, value)
        self.dataChanged.emit(self._game)


# ===========================================================================
# ActorTypeForm -- top-level fields of an actor type (label only, for now)
# ===========================================================================

class ActorTypeForm(QWidget):
    """Edits an actor type's own metadata. Prime sets and extras are edited
    via their own tree nodes / forms; this form just handles the label.
    Adding/removing actor types isn't supported in Tier 1 -- do that in JSON.
    """
    dataChanged = pyqtSignal(dict)

    def __init__(self, actor_type_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._actor_type_id = actor_type_id
        self._at: dict | None = None
        self._suspend = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        head = QLabel(f"<h3>Actor type: <code>{actor_type_id}</code></h3>")
        outer.addWidget(head)

        meta_box = QGroupBox("Actor type")
        form = QFormLayout(meta_box)

        self._label = QLineEdit()
        self._label.setPlaceholderText("Display label, e.g. Character / Scene / Ship")
        self._label.textChanged.connect(lambda v: self._set("label", v))
        form.addRow("Label", self._label)

        outer.addWidget(meta_box)

        info = QLabel(
            "<p>Prime sets and extras are edited through their own tree nodes "
            "below. Right-click a prime sets list to add a new one.</p>"
            "<p>Adding or removing actor types is not supported in this UI yet "
            "\u2014 edit the JSON directly for that.</p>"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 8px;")
        outer.addWidget(info)

        outer.addStretch(1)

    def set_data(self, at: dict) -> None:
        self._at = at
        self._suspend = True
        try:
            self._label.setText(at.get("label", ""))
        finally:
            self._suspend = False

    def _set(self, key: str, value: Any) -> None:
        if self._suspend or self._at is None:
            return
        _set_or_drop(self._at, key, value)
        self.dataChanged.emit(self._at)


# ===========================================================================
# PrimeSetForm -- the big one: id, label, icon, dice, count, settings flags
# ===========================================================================

class PrimeSetForm(QWidget):
    dataChanged = pyqtSignal(dict)

    # Flag definitions:
    #   key             -> (label, default value when first added)
    _FLAGS: list[tuple[str, str, bool]] = [
        ("has_label",       "Trait has a name",                                 True),
        ("has_dice",        "Trait has a die rating",                           True),
        ("has_description", "Trait has a free-text description",                False),
        ("has_statement",   "Trait has a quoted statement (e.g. Values)",       False),
        ("has_sfx",         "Trait can declare SFX",                            False),
        ("has_limits",      "Trait can declare Limits",                         False),
        ("has_sub_traits",  "Trait can have sub-traits (Specialties, Powers)",  False),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ps: dict | None = None
        self._suspend = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ----- Identity ------------------------------------------------
        ident_box = QGroupBox("Prime set")
        ident_form = QFormLayout(ident_box)

        self._id = QLineEdit()
        self._id.setPlaceholderText("snake_case, e.g. distinctions, power_sets")
        self._id.textChanged.connect(lambda v: self._set("id", v))
        ident_form.addRow("ID", self._id)

        self._label = QLineEdit()
        self._label.setPlaceholderText("Display heading, e.g. Distinctions")
        self._label.textChanged.connect(lambda v: self._set("label", v))
        ident_form.addRow("Label", self._label)

        self._icon = IconPicker()
        self._icon.iconChanged.connect(lambda v: self._set("icon", v))
        ident_form.addRow("Icon", self._icon)

        outer.addWidget(ident_box)

        # ----- Counts and dice -----------------------------------------
        dice_box = QGroupBox("Counts && dice")
        dice_form = QFormLayout(dice_box)

        self._count_min = QSpinBox()
        self._count_min.setRange(0, 99)
        self._count_min.valueChanged.connect(self._on_count_changed)

        self._count_max = QSpinBox()
        self._count_max.setRange(-1, 99)
        self._count_max.setSpecialValueText("(no limit)")
        self._count_max.valueChanged.connect(self._on_count_changed)

        count_row = QHBoxLayout()
        count_row.setContentsMargins(0, 0, 0, 0)
        count_row.addWidget(QLabel("min"))
        count_row.addWidget(self._count_min)
        count_row.addSpacing(12)
        count_row.addWidget(QLabel("max"))
        count_row.addWidget(self._count_max)
        count_row.addStretch(1)
        count_wrap = QWidget(); count_wrap.setLayout(count_row)
        dice_form.addRow("Count constraint", count_wrap)

        self._dice = DicePoolEditor()
        self._dice.poolChanged.connect(lambda v: self._set("dice", v or None))
        dice_form.addRow("Allowed dice", self._dice)

        self._default_dice = DicePoolEditor()
        self._default_dice.poolChanged.connect(
            lambda v: self._set("default_dice", v or None)
        )
        dice_form.addRow("Default dice", self._default_dice)

        outer.addWidget(dice_box)

        # ----- Capability flags ---------------------------------------
        flags_box = QGroupBox("Capabilities")
        flags_layout = QVBoxLayout(flags_box)
        self._flag_widgets: dict[str, QCheckBox] = {}
        for key, label, _default in self._FLAGS:
            cb = QCheckBox(label)
            cb.toggled.connect(lambda checked, k=key: self._on_flag_toggled(k, checked))
            flags_layout.addWidget(cb)
            self._flag_widgets[key] = cb
        outer.addWidget(flags_box)

        # ----- Sub-trait sub-config (visible iff has_sub_traits) -------
        self._sub_box = QGroupBox("Sub-traits")
        sub_form = QFormLayout(self._sub_box)

        self._sub_label = QLineEdit()
        self._sub_label.setPlaceholderText('Plural heading, e.g. "Specialties" or "Powers"')
        self._sub_label.textChanged.connect(
            lambda v: self._set_setting("sub_traits_label", v or None)
        )
        sub_form.addRow("Heading label", self._sub_label)

        self._sub_have_dice = QCheckBox("Sub-traits have their own die rating")
        self._sub_have_dice.toggled.connect(
            lambda c: self._set_setting("sub_traits_have_dice", c)
        )
        sub_form.addRow("", self._sub_have_dice)

        self._sub_dice = DicePoolEditor()
        self._sub_dice.poolChanged.connect(
            lambda v: self._set_setting("sub_traits_dice", v or None)
        )
        sub_form.addRow("Allowed sub-trait dice", self._sub_dice)

        self._sub_max = QSpinBox()
        self._sub_max.setRange(-1, 99)
        self._sub_max.setSpecialValueText("(no limit)")
        self._sub_max.valueChanged.connect(self._on_sub_max_changed)
        sub_form.addRow("Max per trait", self._sub_max)

        outer.addWidget(self._sub_box)

        # ----- Limits sub-config (visible iff has_limits) -------------
        self._lim_box = QGroupBox("Limits")
        lim_form = QFormLayout(self._lim_box)
        self._lim_min = QSpinBox()
        self._lim_min.setRange(0, 99)
        self._lim_min.valueChanged.connect(self._on_lim_min_changed)
        lim_form.addRow("Minimum required limits", self._lim_min)
        outer.addWidget(self._lim_box)

        # ----- Predefined items ---------------------------------------
        items_box = QGroupBox("Predefined item names (optional)")
        items_layout = QVBoxLayout(items_box)
        info = QLabel(
            "When set, traits in this prime set must use one of these names "
            "(useful for fixed lists like Mental/Physical/Social). Leave "
            "empty for freeform names."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        items_layout.addWidget(info)
        self._items = NameOnlyListEditor("Item")
        self._items.itemsChanged.connect(
            lambda v: self._set("items", v or None)
        )
        items_layout.addWidget(self._items)
        outer.addWidget(items_box)

        outer.addStretch(1)

    # ----------------------------------------------------------------
    def set_data(self, ps: dict) -> None:
        self._ps = ps
        self._suspend = True
        try:
            self._populate()
        finally:
            self._suspend = False
        # Visibility depends on flags, which we just set; update outside
        # the suspend block since visibility itself isn't a data change.
        self._update_visibility()

    def _populate(self) -> None:
        ps = self._ps or {}
        s = ps.get("settings") or {}

        self._id.setText(ps.get("id", ""))
        self._label.setText(ps.get("label", ""))
        self._icon.set_icon(ps.get("icon", ""))

        c = ps.get("count") or {}
        self._count_min.setValue(int(c.get("min") or 0))
        cmax = c.get("max")
        self._count_max.setValue(int(cmax) if isinstance(cmax, int) else -1)

        self._dice.set_pool(ps.get("dice"))
        self._default_dice.set_pool(ps.get("default_dice"))

        for key, _label, default in self._FLAGS:
            cb = self._flag_widgets[key]
            cb.blockSignals(True)
            cb.setChecked(bool(s.get(key, default)))
            cb.blockSignals(False)

        self._sub_label.setText(s.get("sub_traits_label", "") or "")
        self._sub_have_dice.blockSignals(True)
        self._sub_have_dice.setChecked(bool(s.get("sub_traits_have_dice", True)))
        self._sub_have_dice.blockSignals(False)
        self._sub_dice.set_pool(s.get("sub_traits_dice"))

        smax = s.get("sub_traits_max")
        self._sub_max.blockSignals(True)
        self._sub_max.setValue(int(smax) if isinstance(smax, int) else -1)
        self._sub_max.blockSignals(False)

        lr = s.get("limits_required") or {}
        self._lim_min.blockSignals(True)
        self._lim_min.setValue(int(lr.get("min") or 0))
        self._lim_min.blockSignals(False)

        self._items.set_items(ps.get("items"))

    def _update_visibility(self) -> None:
        s = (self._ps or {}).get("settings") or {}
        self._sub_box.setVisible(bool(s.get("has_sub_traits")))
        self._lim_box.setVisible(bool(s.get("has_limits")))

    # ----- Field-change handlers -----------------------------------
    def _set(self, key: str, value: Any) -> None:
        if self._suspend or self._ps is None:
            return
        _set_or_drop(self._ps, key, value)
        self.dataChanged.emit(self._ps)

    def _set_setting(self, key: str, value: Any) -> None:
        if self._suspend or self._ps is None:
            return
        s = self._ps.setdefault("settings", {})
        _set_or_drop(s, key, value)
        # Don't leave an empty settings dict around
        if not s:
            self._ps.pop("settings", None)
        self.dataChanged.emit(self._ps)

    def _on_flag_toggled(self, flag: str, checked: bool) -> None:
        if self._suspend or self._ps is None:
            return
        s = self._ps.setdefault("settings", {})
        s[flag] = checked
        # Clean up dependent fields when their gate flag goes off, so the
        # JSON stays minimal.
        if flag == "has_sub_traits" and not checked:
            for k in ("sub_traits_label", "sub_traits_have_dice",
                      "sub_traits_dice", "sub_traits_max"):
                s.pop(k, None)
        if flag == "has_limits" and not checked:
            s.pop("limits_required", None)
        self._update_visibility()
        self.dataChanged.emit(self._ps)

    def _on_count_changed(self, _val: int) -> None:
        if self._suspend or self._ps is None:
            return
        cmin = self._count_min.value()
        cmax = self._count_max.value()
        out: dict = {}
        if cmin > 0:
            out["min"] = cmin
        if cmax != -1:
            out["max"] = cmax
        if out:
            self._ps["count"] = out
        else:
            self._ps.pop("count", None)
        self.dataChanged.emit(self._ps)

    def _on_sub_max_changed(self, val: int) -> None:
        self._set_setting("sub_traits_max", val if val != -1 else None)

    def _on_lim_min_changed(self, val: int) -> None:
        if self._suspend or self._ps is None:
            return
        s = self._ps.setdefault("settings", {})
        if val > 0:
            s["limits_required"] = {"min": val}
        else:
            s.pop("limits_required", None)
        self.dataChanged.emit(self._ps)


# ===========================================================================
# ExtrasForm -- per-actor-type extras: stress, milestones, plot points
# ===========================================================================

class ExtrasForm(QWidget):
    dataChanged = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._extras: dict | None = None
        self._suspend = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # ----- Stress --------------------------------------------------
        stress_box = QGroupBox("Stress tracks")
        stress_layout = QVBoxLayout(stress_box)

        self._stress_enabled = QCheckBox("Enable stress")
        self._stress_enabled.toggled.connect(self._on_stress_enabled)
        stress_layout.addWidget(self._stress_enabled)

        self._trauma_enabled = QCheckBox("Enable trauma alongside stress")
        self._trauma_enabled.toggled.connect(self._on_trauma_enabled)
        stress_layout.addWidget(self._trauma_enabled)

        # Tracks editor (id + label rows). We use NameOnlyListEditor for the
        # label-only field but stress tracks need both id and label, so we
        # build inline rows here.
        self._tracks_inner = QWidget()
        self._tracks_layout = QVBoxLayout(self._tracks_inner)
        self._tracks_layout.setContentsMargins(0, 0, 0, 0)
        self._tracks_layout.setSpacing(2)
        stress_layout.addWidget(self._tracks_inner)

        self._add_track_btn = QPushButton("+ Add stress track")
        self._add_track_btn.clicked.connect(self._on_add_track)
        stress_layout.addWidget(self._add_track_btn)

        outer.addWidget(stress_box)

        # ----- Milestones ---------------------------------------------
        ms_box = QGroupBox("Milestones")
        ms_layout = QVBoxLayout(ms_box)
        self._ms_enabled = QCheckBox("Enable milestones")
        self._ms_enabled.toggled.connect(self._on_ms_enabled)
        ms_layout.addWidget(self._ms_enabled)
        outer.addWidget(ms_box)

        # ----- Plot points --------------------------------------------
        pp_box = QGroupBox("Plot points")
        pp_form = QFormLayout(pp_box)
        self._pp_enabled = QCheckBox("Enable plot points")
        self._pp_enabled.toggled.connect(self._on_pp_enabled)
        pp_form.addRow(self._pp_enabled)

        self._pp_starting = QSpinBox()
        self._pp_starting.setRange(0, 99)
        self._pp_starting.valueChanged.connect(self._on_pp_starting)
        pp_form.addRow("Starting plot points", self._pp_starting)
        outer.addWidget(pp_box)

        # ----- Complications ------------------------------------------
        comp_box = QGroupBox("Complications")
        comp_layout = QVBoxLayout(comp_box)
        self._comp_enabled = QCheckBox("Enable complications section")
        self._comp_enabled.toggled.connect(self._on_comp_enabled)
        comp_layout.addWidget(self._comp_enabled)
        comp_info = QLabel(
            "Step-rated traits picked up during play. When enabled, the PDF "
            "always renders this section \u2014 reserving printable blank "
            "space for pen-and-paper notation if no complications are recorded."
        )
        comp_info.setWordWrap(True)
        comp_info.setStyleSheet("color: #666; padding-left: 18px;")
        comp_layout.addWidget(comp_info)
        outer.addWidget(comp_box)

        outer.addStretch(1)

    # ----------------------------------------------------------------
    def set_data(self, extras: dict) -> None:
        self._extras = extras
        self._suspend = True
        try:
            stress = extras.get("stress") or {}
            self._stress_enabled.setChecked(bool(stress.get("enabled")))
            self._trauma_enabled.setChecked(bool(stress.get("trauma_enabled")))
            self._rebuild_tracks(stress.get("tracks") or [])

            ms = extras.get("milestones") or {}
            self._ms_enabled.setChecked(bool(ms.get("enabled")))

            pp = extras.get("plot_points") or {}
            self._pp_enabled.setChecked(bool(pp.get("enabled")))
            self._pp_starting.setValue(int(pp.get("starting") or 0))

            comp = extras.get("complications") or {}
            self._comp_enabled.setChecked(bool(comp.get("enabled")))
        finally:
            self._suspend = False

    # ----- Stress tracks (inline rows) ------------------------------
    def _rebuild_tracks(self, tracks: list[dict]) -> None:
        # Clear existing rows
        while self._tracks_layout.count():
            it = self._tracks_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

        # Reload from data (forms hold no copy of their own; the dict in
        # extras["stress"]["tracks"] is the source of truth).
        for i, _t in enumerate(tracks):
            self._tracks_layout.addWidget(self._make_track_row(i))

    def _make_track_row(self, index: int) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        tracks = self._tracks()
        t = tracks[index] if index < len(tracks) else {}

        id_edit = QLineEdit(t.get("id", ""))
        id_edit.setPlaceholderText("id")
        id_edit.textChanged.connect(lambda v, i=index: self._update_track(i, "id", v))
        h.addWidget(id_edit, 1)

        label_edit = QLineEdit(t.get("label", ""))
        label_edit.setPlaceholderText("Label")
        label_edit.textChanged.connect(lambda v, i=index: self._update_track(i, "label", v))
        h.addWidget(label_edit, 2)

        rm = QPushButton("\u2715")
        rm.setFixedWidth(24)
        rm.clicked.connect(lambda _c, i=index: self._remove_track(i))
        h.addWidget(rm)
        return wrap

    def _tracks(self) -> list:
        if self._extras is None:
            return []
        return self._extras.setdefault("stress", {}).setdefault("tracks", [])

    def _on_add_track(self) -> None:
        if self._suspend or self._extras is None:
            return
        self._tracks().append({"id": "", "label": ""})
        self._rebuild_tracks(self._tracks())
        self.dataChanged.emit(self._extras)

    def _remove_track(self, index: int) -> None:
        if self._suspend or self._extras is None:
            return
        tracks = self._tracks()
        if 0 <= index < len(tracks):
            del tracks[index]
            self._rebuild_tracks(tracks)
            self.dataChanged.emit(self._extras)

    def _update_track(self, index: int, field: str, value: str) -> None:
        if self._suspend or self._extras is None:
            return
        tracks = self._tracks()
        if 0 <= index < len(tracks):
            tracks[index][field] = value
            self.dataChanged.emit(self._extras)

    # ----- Stress / milestones / plot-points enable toggles ---------
    def _on_stress_enabled(self, checked: bool) -> None:
        if self._suspend or self._extras is None:
            return
        self._extras.setdefault("stress", {})["enabled"] = checked
        self.dataChanged.emit(self._extras)

    def _on_trauma_enabled(self, checked: bool) -> None:
        if self._suspend or self._extras is None:
            return
        self._extras.setdefault("stress", {})["trauma_enabled"] = checked
        self.dataChanged.emit(self._extras)

    def _on_ms_enabled(self, checked: bool) -> None:
        if self._suspend or self._extras is None:
            return
        self._extras.setdefault("milestones", {})["enabled"] = checked
        self.dataChanged.emit(self._extras)

    def _on_pp_enabled(self, checked: bool) -> None:
        if self._suspend or self._extras is None:
            return
        self._extras.setdefault("plot_points", {})["enabled"] = checked
        self.dataChanged.emit(self._extras)

    def _on_pp_starting(self, val: int) -> None:
        if self._suspend or self._extras is None:
            return
        self._extras.setdefault("plot_points", {})["starting"] = val
        self.dataChanged.emit(self._extras)

    def _on_comp_enabled(self, checked: bool) -> None:
        if self._suspend or self._extras is None:
            return
        self._extras.setdefault("complications", {})["enabled"] = checked
        self.dataChanged.emit(self._extras)

"""Left-pane section navigator.

Lists every section the character has (or could have, per the actor type
definition):

    Identity
    Distinctions   (3)
    Attributes     (3)
    Skills         (6)
    Values         (6)
    Signature Items (2)
    Power Sets     (1)
    --
    Stress
    Milestones     (1)
    Notes

Sections that the character has data for show their count. Empty/unused
sections are still listed so the user can navigate to them and add entries.

Emits `sectionSelected(kind, id)`:
    kind = "identity" | "prime_set" | "stress" | "milestones" | "notes"
    id   = the prime_set id, or "" for non-prime-set sections
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem


# Roles for stuffing payload data on QListWidgetItem.
KIND_ROLE = Qt.ItemDataRole.UserRole + 1
ID_ROLE   = Qt.ItemDataRole.UserRole + 2


class SectionList(QListWidget):
    sectionSelected = pyqtSignal(str, str)  # kind, id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setUniformItemSizes(True)
        self.setMinimumWidth(180)
        self.itemSelectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------------
    def populate(self, actor_type_def: dict, character: dict) -> None:
        """Rebuild the list from the actor-type definition + character data."""
        self.clear()

        char_prime_sets = character.get("prime_sets") or {}

        self._add_item("Identity", "identity", "")

        for ps in actor_type_def.get("prime_sets", []):
            ps_id = ps.get("id", "")
            label = ps.get("label", ps_id) or ps_id
            entries = char_prime_sets.get(ps_id) or []
            count = len(entries)
            display = f"{label}    ({count})" if count else f"{label}    (empty)"
            self._add_item(display, "prime_set", ps_id, dim=count == 0)

        # Extras
        extras_def = actor_type_def.get("extras") or {}
        char_extras = character.get("extras") or {}

        # Visual divider
        sep = QListWidgetItem("\u2500" * 18)
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setForeground(Qt.GlobalColor.gray)
        self.addItem(sep)

        if extras_def.get("stress", {}).get("enabled"):
            self._add_item("Stress", "stress", "")

        if extras_def.get("milestones", {}).get("enabled"):
            n = len(char_extras.get("milestones") or [])
            label = f"Milestones    ({n})" if n else "Milestones    (empty)"
            self._add_item(label, "milestones", "", dim=n == 0)

        if extras_def.get("growth", {}).get("enabled"):
            n = len(char_extras.get("growth") or [])
            label = f"Growth    ({n})" if n else "Growth    (empty)"
            self._add_item(label, "growth", "", dim=n == 0)

        if extras_def.get("sessions", {}).get("enabled"):
            n = len(char_extras.get("sessions") or [])
            label = f"Sessions    ({n})" if n else "Sessions    (empty)"
            self._add_item(label, "sessions", "", dim=n == 0)

        if extras_def.get("complications", {}).get("enabled"):
            n = len(char_extras.get("complications") or [])
            label = f"Complications    ({n})" if n else "Complications    (empty)"
            self._add_item(label, "complications", "", dim=n == 0)

        # Notes is always available -- it's just free text.
        self._add_item("Notes", "notes", "", dim=not character.get("notes"))

        # Default selection: Identity.
        if self.count() > 0:
            self.setCurrentRow(0)

    # ------------------------------------------------------------------
    def update_counts(self, actor_type_def: dict, character: dict) -> None:
        """Refresh entry counts and dim states without rebuilding the list.

        Called from the main window on every edit. Critical that this
        does NOT touch selection or fire any signals -- otherwise the
        focus on the field the user is currently typing into gets reset
        to position 0 (which makes QPlainTextEdit type backwards) or
        lost entirely (the "bouncing cursor" symptom on QLineEdit).
        """
        char_prime_sets = character.get("prime_sets") or {}
        char_extras = character.get("extras") or {}

        for row in range(self.count()):
            item = self.item(row)
            kind = item.data(KIND_ROLE)
            id_ = item.data(ID_ROLE) or ""

            if kind == "prime_set":
                ps_def = next(
                    (ps for ps in actor_type_def.get("prime_sets", [])
                     if ps.get("id") == id_),
                    None,
                )
                if ps_def is None:
                    continue
                label = ps_def.get("label", id_) or id_
                count = len(char_prime_sets.get(id_) or [])
                item.setText(f"{label}    ({count})" if count else f"{label}    (empty)")
                item.setForeground(
                    Qt.GlobalColor.gray if count == 0 else self.palette().windowText()
                )

            elif kind == "milestones":
                n = len(char_extras.get("milestones") or [])
                item.setText(f"Milestones    ({n})" if n else "Milestones    (empty)")
                item.setForeground(
                    Qt.GlobalColor.gray if n == 0 else self.palette().windowText()
                )

            elif kind == "growth":
                n = len(char_extras.get("growth") or [])
                item.setText(f"Growth    ({n})" if n else "Growth    (empty)")
                item.setForeground(
                    Qt.GlobalColor.gray if n == 0 else self.palette().windowText()
                )

            elif kind == "sessions":
                n = len(char_extras.get("sessions") or [])
                item.setText(f"Sessions    ({n})" if n else "Sessions    (empty)")
                item.setForeground(
                    Qt.GlobalColor.gray if n == 0 else self.palette().windowText()
                )

            elif kind == "complications":
                n = len(char_extras.get("complications") or [])
                item.setText(f"Complications    ({n})" if n else "Complications    (empty)")
                item.setForeground(
                    Qt.GlobalColor.gray if n == 0 else self.palette().windowText()
                )

            elif kind == "notes":
                has_notes = bool(character.get("notes"))
                item.setForeground(
                    self.palette().windowText() if has_notes else Qt.GlobalColor.gray
                )

    # ------------------------------------------------------------------
    def _add_item(self, label: str, kind: str, id_: str, *, dim: bool = False) -> None:
        item = QListWidgetItem(label)
        item.setData(KIND_ROLE, kind)
        item.setData(ID_ROLE, id_)
        if dim:
            item.setForeground(Qt.GlobalColor.gray)
        self.addItem(item)

    def _on_selection(self) -> None:
        item = self.currentItem()
        if item is None:
            return
        kind = item.data(KIND_ROLE)
        id_ = item.data(ID_ROLE)
        if kind:  # ignore the divider
            self.sectionSelected.emit(kind, id_ or "")

    # ------------------------------------------------------------------
    def select(self, kind: str, id_: str = "") -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(KIND_ROLE) == kind and (item.data(ID_ROLE) or "") == id_:
                self.setCurrentRow(row)
                return

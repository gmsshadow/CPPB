"""Tests for prime-set reordering in the game-definition editor.

The renderer reads prime-set order directly, so the editor's Move
Up / Move Down is how a user controls section stacking on the sheet.
These tests exercise the reorder logic and its edge cases.
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    from cortex_portfolio.editor.game_def_window import GameDefWindow
    win = GameDefWindow()
    win._game = json.loads((_EXAMPLES / "xadia.game.json").read_text())
    win._refresh_tree()
    return win


def _ids(win, at="character"):
    return [ps["id"] for ps in win._game["actor_types"][at]["prime_sets"]]


class TestMovePrimeSet:
    def test_move_up_swaps_with_previous(self, window):
        before = _ids(window)
        target = before[2]
        window._move_prime_set("character", target, -1)
        after = _ids(window)
        assert after[1] == target
        assert after[2] == before[1]

    def test_move_down_swaps_with_next(self, window):
        before = _ids(window)
        target = before[2]
        window._move_prime_set("character", target, +1)
        after = _ids(window)
        assert after[3] == target
        assert after[2] == before[3]

    def test_round_trip_restores_order(self, window):
        before = _ids(window)
        target = before[2]
        window._move_prime_set("character", target, -1)
        window._move_prime_set("character", target, +1)
        assert _ids(window) == before

    def test_move_first_up_is_noop(self, window):
        before = _ids(window)
        window._move_prime_set("character", before[0], -1)
        assert _ids(window) == before

    def test_move_last_down_is_noop(self, window):
        before = _ids(window)
        window._move_prime_set("character", before[-1], +1)
        assert _ids(window) == before

    def test_unknown_id_is_noop(self, window):
        before = _ids(window)
        window._move_prime_set("character", "no_such_prime_set", -1)
        assert _ids(window) == before

    def test_move_marks_dirty(self, window):
        window._dirty = False
        before = _ids(window)
        window._move_prime_set("character", before[1], -1)
        assert window._dirty is True

    def test_noop_move_does_not_falsely_dirty(self, window):
        # Moving the first item up changes nothing -- but the current
        # implementation returns before touching _dirty, so a no-op move
        # should leave a clean document clean.
        window._dirty = False
        before = _ids(window)
        window._move_prime_set("character", before[0], -1)
        assert window._dirty is False

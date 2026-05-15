"""Tests for `settings.render_when_empty` on prime sets.

By default an empty prime set is skipped entirely. With the flag on, the
section renders its heading + writing-lines block so players can fill it
in by hand at the table.
"""
import copy
import json
from pathlib import Path

import pytest

from cortex_portfolio.render import resolve_actor_type, build_rows
from cortex_portfolio.validate import validate, split, KNOWN_SETTINGS_FLAGS

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def hammerheads_game():
    return json.loads((_EXAMPLES / "hammerheads.game.json").read_text())


@pytest.fixture
def reyes_character():
    return json.loads((_EXAMPLES / "reyes.character.json").read_text())


class TestRenderWhenEmpty:
    def test_flag_is_a_known_settings_flag(self):
        # Else every game-def using it gets a spurious unknown-flag warning.
        assert "render_when_empty" in KNOWN_SETTINGS_FLAGS

    def test_empty_set_is_skipped_by_default(self, hammerheads_game,
                                             reyes_character):
        # Default behaviour: empty prime set produces no section.
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["distinctions"] = []
        at = resolve_actor_type(hammerheads_game, ch.get("actor_type"))
        rows = build_rows(at, ch)
        labels = [sec["label"] for row in rows for sec in row]
        assert "Distinctions" not in labels

    def test_empty_set_renders_when_flag_on(self, hammerheads_game,
                                            reyes_character):
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "distinctions":
                ps["settings"]["render_when_empty"] = True
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["distinctions"] = []
        at = resolve_actor_type(g, ch.get("actor_type"))
        rows = build_rows(at, ch)
        labels = [sec["label"] for row in rows for sec in row]
        assert "Distinctions" in labels
        # And the section's data list is empty -- the template uses that
        # to switch to the writing-lines rendering.
        distinctions = next(
            sec for row in rows for sec in row if sec["label"] == "Distinctions"
        )
        assert distinctions["data"] == []

    def test_populated_set_unaffected_by_flag(self, hammerheads_game,
                                              reyes_character):
        # When the character DOES have entries, the flag changes nothing:
        # the section renders its traits normally.
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "distinctions":
                ps["settings"]["render_when_empty"] = True
        at = resolve_actor_type(g, reyes_character.get("actor_type"))
        rows = build_rows(at, reyes_character)
        distinctions = next(
            sec for row in rows for sec in row if sec["label"] == "Distinctions"
        )
        assert len(distinctions["data"]) == len(
            reyes_character["prime_sets"]["distinctions"]
        )

    def test_writing_lines_in_html(self, hammerheads_game, reyes_character,
                                   render_html):
        # End-to-end: the empty section's HTML contains the writing-lines
        # block, not an empty trait list.
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "distinctions":
                ps["settings"]["render_when_empty"] = True
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["distinctions"] = []
        html = render_html(g, ch)
        assert 'class="prime-set-blank"' in html
        # And the heading rendered too, not just the lines.
        assert "DISTINCTIONS" in html.upper() or "Distinctions" in html

    def test_validator_accepts_flag(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "distinctions":
                ps["settings"]["render_when_empty"] = True
        errs, warns = split(validate(g))
        assert errs == []
        assert not any("render_when_empty" in w.message for w in warns)

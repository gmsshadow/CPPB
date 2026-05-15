"""Tests for the Stricken & Shaken stress box.

The box is worksheet-only scaffolding: when a prime set's settings have
has_stress_box, every parent trait in that set renders a small empty
square next to its die. Sub-traits never get one. No JSON value -- the
box is always empty in the rendered PDF.
"""
import copy
import json
from pathlib import Path

import pytest

from cortex_portfolio.validate import validate, split, KNOWN_SETTINGS_FLAGS

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def hammerheads_game():
    return json.loads((_EXAMPLES / "hammerheads.game.json").read_text())


@pytest.fixture
def reyes_character():
    return json.loads((_EXAMPLES / "reyes.character.json").read_text())


class TestStressBoxValidation:
    def test_flag_is_recognized(self):
        # has_stress_box must be a known settings flag, else every game-def
        # that uses it gets a spurious "unknown flag" warning.
        assert "has_stress_box" in KNOWN_SETTINGS_FLAGS

    def test_enabling_flag_does_not_warn(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "attributes":
                ps["settings"]["has_stress_box"] = True
        errs, warns = split(validate(g))
        assert errs == []
        assert not any("has_stress_box" in w.message for w in warns)


class TestStressBoxRendering:
    def test_box_renders_when_flag_on(self, hammerheads_game, reyes_character,
                                      render_html):
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "attributes":
                ps["settings"]["has_stress_box"] = True
        html = render_html(g, reyes_character)
        assert 'class="stress-box"' in html

    def test_no_box_when_flag_off(self, hammerheads_game, reyes_character,
                                  render_html):
        # Stock hammerheads has no stress boxes anywhere.
        html = render_html(hammerheads_game, reyes_character)
        assert 'class="stress-box"' not in html

    def test_box_count_matches_parent_traits_only(self, hammerheads_game,
                                                  reyes_character, render_html):
        # Enable on skills, which has a sub-trait (Fly -> Dogfighting).
        # The box count must equal the number of *parent* skill traits,
        # NOT counting the sub-trait.
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "skills":
                ps["settings"]["has_stress_box"] = True
        n_parent_skills = len(reyes_character["prime_sets"]["skills"])
        html = render_html(g, reyes_character)
        assert html.count('class="stress-box"') == n_parent_skills

    def test_box_is_empty(self, hammerheads_game, reyes_character, render_html):
        # Worksheet-only: the box must render with no content inside it.
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "attributes":
                ps["settings"]["has_stress_box"] = True
        html = render_html(g, reyes_character)
        # The span should be self-contained / empty: '<span class="stress-box" ...></span>'
        assert 'class="stress-box"' in html
        # No digits or dice glyphs smuggled in -- find each occurrence and
        # confirm it closes immediately.
        import re
        for m in re.finditer(r'<span class="stress-box"[^>]*>(.*?)</span>', html):
            assert m.group(1).strip() == "", f"stress-box not empty: {m.group(1)!r}"

    def test_flag_only_affects_its_own_prime_set(self, hammerheads_game,
                                                 reyes_character, render_html):
        # Enabling the box on attributes must not put boxes on distinctions.
        g = copy.deepcopy(hammerheads_game)
        for ps in g["actor_types"]["character"]["prime_sets"]:
            if ps["id"] == "attributes":
                ps["settings"]["has_stress_box"] = True
        html = render_html(g, reyes_character)
        # Attributes has 3 traits; distinctions has 3 but no flag.
        # Total boxes should equal attribute count exactly.
        n_attrs = len(reyes_character["prime_sets"]["attributes"])
        assert html.count('class="stress-box"') == n_attrs

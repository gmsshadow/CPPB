"""Tests for the optional XP track.

The track is worksheet scaffolding (no per-character value), so the
tests cover: validator shape-checking, and that the renderer emits the
right number of pips when the actor type enables it.
"""
import copy
import json
from pathlib import Path

import pytest

from cortex_portfolio.validate import validate, split


_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def hammerheads_game():
    return json.loads((_EXAMPLES / "hammerheads.game.json").read_text())


class TestXpTrackValidation:
    def test_valid_xp_track_is_clean(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = {
            "enabled": True, "pips": 17, "label": "XP",
        }
        errs, warns = split(validate(g))
        assert errs == []
        xp_warns = [w for w in warns if "xp_track" in w.path]
        assert xp_warns == []

    def test_pips_must_be_integer(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = {
            "enabled": True, "pips": "seventeen",
        }
        errs, _ = split(validate(g))
        assert any("xp_track.pips" in e.path for e in errs)

    def test_pips_must_be_positive(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = {
            "enabled": True, "pips": 0,
        }
        errs, _ = split(validate(g))
        assert any("xp_track.pips" in e.path for e in errs)

    def test_huge_pip_count_warns(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = {
            "enabled": True, "pips": 200,
        }
        errs, warns = split(validate(g))
        assert errs == []
        assert any("xp_track.pips" in w.path for w in warns)

    def test_xp_track_must_be_mapping(self, hammerheads_game):
        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = "yes"
        errs, _ = split(validate(g))
        assert any("xp_track" in e.path for e in errs)

    def test_pips_optional_defaults_handled(self, hammerheads_game):
        # enabled with no pips key: valid (renderer falls back to 17).
        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = {
            "enabled": True,
        }
        errs, warns = split(validate(g))
        assert errs == []
        assert [w for w in warns if "xp_track" in w.path] == []


class TestXpTrackRendering:
    def test_track_renders_correct_pip_count(self, hammerheads_game, tmp_path):
        # Render to HTML (not PDF) so we can count pip elements directly.
        from cortex_portfolio.render import (
            resolve_actor_type, build_rows,
        )
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        from cortex_portfolio.render import (
            dice_icons, inline_glyphs, icon_glyph, assets_dir,
        )

        g = copy.deepcopy(hammerheads_game)
        g["actor_types"]["character"].setdefault("extras", {})["xp_track"] = {
            "enabled": True, "pips": 12,
        }
        character = json.loads((_EXAMPLES / "reyes.character.json").read_text())
        at = resolve_actor_type(g, character.get("actor_type"))

        templates_dir = assets_dir() / "templates"
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True, lstrip_blocks=True,
        )
        env.filters["dice"] = dice_icons
        env.filters["inline_glyphs"] = inline_glyphs
        env.globals["icon_glyph"] = icon_glyph
        html = env.get_template("sheet.html.j2").render(
            game=g, actor_type=at, character=character,
            rows=build_rows(at, character),
        )
        assert html.count('class="xp-pip"') == 12
        assert "has-xp-track" in html

    def test_no_track_when_disabled(self, hammerheads_game):
        from cortex_portfolio.render import (
            resolve_actor_type, build_rows, dice_icons, inline_glyphs,
            icon_glyph, assets_dir,
        )
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        # hammerheads.game.json has no xp_track -> none should render.
        character = json.loads((_EXAMPLES / "reyes.character.json").read_text())
        at = resolve_actor_type(hammerheads_game, character.get("actor_type"))
        templates_dir = assets_dir() / "templates"
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True, lstrip_blocks=True,
        )
        env.filters["dice"] = dice_icons
        env.filters["inline_glyphs"] = inline_glyphs
        env.globals["icon_glyph"] = icon_glyph
        html = env.get_template("sheet.html.j2").render(
            game=hammerheads_game, actor_type=at, character=character,
            rows=build_rows(at, character),
        )
        assert 'class="xp-pip"' not in html
        assert "has-xp-track" not in html

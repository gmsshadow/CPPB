"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def hammerheads_game() -> dict:
    return _load("hammerheads.game.json")


@pytest.fixture
def vigilant_game() -> dict:
    return _load("vigilant.game.json")


@pytest.fixture
def xadia_game() -> dict:
    return _load("xadia.game.json")


@pytest.fixture
def reyes_character() -> dict:
    return _load("reyes.character.json")


@pytest.fixture
def harker_character() -> dict:
    return _load("harker.character.json")


@pytest.fixture
def black_sea_character() -> dict:
    return _load("black_sea.character.json")


@pytest.fixture
def timba_character() -> dict:
    return _load("timba.character.json")


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture
def render_html():
    """Render a game-def + character to the raw HTML string (no PDF step).

    Lets template tests assert on markup directly without each one
    re-creating the Jinja environment. Mirrors render_pdf's env setup.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from cortex_portfolio.render import (
        resolve_actor_type, build_rows, dice_icons, inline_glyphs,
        icon_glyph, assets_dir,
    )

    def _render(game: dict, character: dict) -> str:
        at = resolve_actor_type(game, character.get("actor_type"))
        templates_dir = assets_dir() / "templates"
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True, lstrip_blocks=True,
        )
        env.filters["dice"] = dice_icons
        env.filters["inline_glyphs"] = inline_glyphs
        env.globals["icon_glyph"] = icon_glyph
        return env.get_template("sheet.html.j2").render(
            game=game, actor_type=at, character=character,
            rows=build_rows(at, character),
        )

    return _render

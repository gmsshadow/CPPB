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
def reyes_character() -> dict:
    return _load("reyes.character.json")


@pytest.fixture
def harker_character() -> dict:
    return _load("harker.character.json")


@pytest.fixture
def black_sea_character() -> dict:
    return _load("black_sea.character.json")


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR

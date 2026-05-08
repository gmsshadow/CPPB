"""Tests for validate.py.

Heavily uses the bundled example data: those files MUST validate cleanly,
because they're the canonical reference for the schema.
"""
from __future__ import annotations

import copy

import pytest

from cortex_portfolio.validate import Issue, validate, split


# ---------------------------------------------------------------------------
# Examples must validate cleanly. If they don't, the schema and the docs
# have drifted apart -- the regression test is the whole point.
# ---------------------------------------------------------------------------

class TestBundledExamplesValidate:
    def test_reyes_against_hammerheads(self, hammerheads_game, reyes_character):
        assert validate(hammerheads_game, reyes_character) == []

    def test_black_sea_against_hammerheads(self, hammerheads_game, black_sea_character):
        assert validate(hammerheads_game, black_sea_character) == []

    def test_harker_against_vigilant(self, vigilant_game, harker_character):
        assert validate(vigilant_game, harker_character) == []

    def test_game_def_alone_validates(self, hammerheads_game):
        # No character -> only game-def-level checks run.
        assert validate(hammerheads_game) == []


# ---------------------------------------------------------------------------
# Game-def-level errors
# ---------------------------------------------------------------------------

class TestGameDefinitionValidation:
    def test_missing_top_level_fields_are_errors(self):
        issues = validate({})
        errs, _ = split(issues)
        paths = {i.path for i in errs}
        assert "game.id" in paths
        assert "game.name" in paths
        assert "game.actor_types" in paths

    def test_dice_pool_must_be_a_list(self):
        gd = {
            "id": "x", "name": "X",
            "dice_pool": "d4-d12",
            "actor_types": {"character": {"label": "C", "prime_sets": []}},
        }
        errs, _ = split(validate(gd))
        assert any(e.path == "game.dice_pool" for e in errs)

    def test_unrecognized_die_in_pool_is_warning(self):
        gd = {
            "id": "x", "name": "X",
            "dice_pool": ["d4", "d20"],
            "actor_types": {"character": {"label": "C", "prime_sets": []}},
        }
        _, warns = split(validate(gd))
        assert any("d20" in w.message for w in warns)

    def test_duplicate_prime_set_id_is_error(self):
        gd = {
            "id": "x", "name": "X",
            "dice_pool": ["d4", "d6", "d8"],
            "actor_types": {
                "character": {
                    "label": "C",
                    "prime_sets": [
                        {"id": "dupe", "label": "First",  "settings": {}},
                        {"id": "dupe", "label": "Second", "settings": {}},
                    ],
                }
            },
        }
        errs, _ = split(validate(gd))
        assert any(e.path.endswith(".id") and "duplicate" in e.message for e in errs)

    def test_unknown_settings_flag_is_warning(self):
        gd = {
            "id": "x", "name": "X",
            "dice_pool": ["d8"],
            "actor_types": {
                "character": {
                    "label": "C",
                    "prime_sets": [
                        {"id": "ps", "label": "PS", "settings": {"has_hubris": True}},
                    ],
                }
            },
        }
        _, warns = split(validate(gd))
        assert any("has_hubris" in w.message for w in warns)

    def test_count_min_greater_than_max_is_error(self):
        gd = {
            "id": "x", "name": "X",
            "dice_pool": ["d8"],
            "actor_types": {
                "character": {
                    "label": "C",
                    "prime_sets": [
                        {"id": "ps", "label": "PS", "settings": {},
                         "count": {"min": 5, "max": 2}},
                    ],
                }
            },
        }
        errs, _ = split(validate(gd))
        assert any(e.path.endswith(".count") for e in errs)


# ---------------------------------------------------------------------------
# Character-level cross-validation (the most likely source of user mistakes)
# ---------------------------------------------------------------------------

class TestCharacterValidation:
    def test_unknown_actor_type_is_blocking_error(self, hammerheads_game):
        ch = {"actor_type": "starship_captain", "prime_sets": {}}
        errs, _ = split(validate(hammerheads_game, ch))
        assert any(e.path == "character.actor_type" for e in errs)
        # Cross-check: this is the ONLY common character problem that should
        # actually block, because the renderer can't proceed without an
        # actor type definition.
        assert all(e.path == "character.actor_type" for e in errs)

    def test_d20_in_character_is_warning_not_error(
        self, hammerheads_game, reyes_character
    ):
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["attributes"][0]["dice"] = ["d20"]
        errs, warns = split(validate(hammerheads_game, ch))
        assert errs == []
        assert any("d20" in w.message for w in warns)

    def test_string_dice_flagged_as_v1_leftover(
        self, hammerheads_game, reyes_character
    ):
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["attributes"][0]["dice"] = "d6"
        _, warns = split(validate(hammerheads_game, ch))
        assert any("v1 leftover" in w.message for w in warns)

    def test_count_min_violation_is_warning(
        self, hammerheads_game, reyes_character
    ):
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["distinctions"] = ch["prime_sets"]["distinctions"][:1]
        errs, warns = split(validate(hammerheads_game, ch))
        assert errs == []
        assert any(
            w.path == "character.prime_sets.distinctions"
            and "minimum" in w.message
            for w in warns
        )

    def test_undefined_prime_set_is_warning(self, hammerheads_game, reyes_character):
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["ghosts"] = [{"name": "Spectre", "dice": ["d6"]}]
        _, warns = split(validate(hammerheads_game, ch))
        assert any("ghosts" in w.path and "not defined" in w.message for w in warns)

    def test_undefined_stress_track_is_warning(
        self, hammerheads_game, reyes_character
    ):
        ch = copy.deepcopy(reyes_character)
        ch["extras"]["stress"]["psionic"] = "d6"
        _, warns = split(validate(hammerheads_game, ch))
        assert any(
            w.path == "character.extras.stress.psionic"
            and "undefined stress track" in w.message
            for w in warns
        )

    def test_sfx_on_non_sfx_prime_set_is_warning(
        self, hammerheads_game, reyes_character
    ):
        # Skills don't allow SFX in the Hammerheads preset.
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["skills"][0]["sfx"] = [
            {"name": "Bonus", "text": "Should not be here"}
        ]
        _, warns = split(validate(hammerheads_game, ch))
        assert any(
            "skills[0].sfx" in w.path and "has_sfx is false" in w.message
            for w in warns
        )

    def test_predefined_items_are_suggestions_not_constraints(
        self, hammerheads_game, reyes_character
    ):
        # Hammerheads attributes have a predefined items list (Mental,
        # Physical, Social). The editor lets users type their own names
        # over those defaults, so the validator deliberately does NOT
        # warn when a name doesn't match the predefined list -- the items
        # list is a dropdown of suggestions, not a constraint.
        ch = copy.deepcopy(reyes_character)
        ch["prime_sets"]["attributes"][0]["name"] = "Charisma"
        errs, warns = split(validate(hammerheads_game, ch))
        assert errs == []
        assert not any("Charisma" in w.message for w in warns), \
            "Custom names over predefined items should not trigger warnings"

    def test_game_definition_id_mismatch_is_warning(
        self, hammerheads_game, reyes_character
    ):
        ch = copy.deepcopy(reyes_character)
        ch["game_definition"] = "wrong-id"
        _, warns = split(validate(hammerheads_game, ch))
        assert any(w.path == "character.game_definition" for w in warns)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

class TestPublicAPI:
    def test_issue_is_immutable_dataclass(self):
        i = Issue("error", "x.y", "msg")
        assert i.is_error()
        with pytest.raises(Exception):  # frozen dataclass -> FrozenInstanceError
            i.severity = "warning"  # type: ignore[misc]

    def test_split_partitions_correctly(self):
        issues = [
            Issue("error",   "a", "e1"),
            Issue("warning", "b", "w1"),
            Issue("error",   "c", "e2"),
        ]
        errs, warns = split(issues)
        assert [i.path for i in errs]  == ["a", "c"]
        assert [i.path for i in warns] == ["b"]

    def test_no_character_means_only_game_def_checks(self, hammerheads_game):
        # Mutating the character fixture cannot make game-def validation fail.
        assert validate(hammerheads_game, None) == validate(hammerheads_game)

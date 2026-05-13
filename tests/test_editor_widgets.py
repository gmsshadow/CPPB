"""Smoke tests for editor widgets.

These tests just instantiate each main form/widget under offscreen Qt
and verify they construct without raising. That's much weaker than
exercising real interactions, but it's enough to catch the kind of
"forgot to import a symbol" regression that bit the ColorPicker --
NameError on instantiation isn't visible until the user navigates to
the affected tree node, which can be a long time after the fact.

If pytest-qt were a dep we'd write proper interaction tests; for now
keep it lightweight and don't add new install requirements.
"""
import os
import pytest

# Run Qt offscreen so we can instantiate widgets without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    """Single QApplication for all the widget tests in this module."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


class TestGameDefForms:
    def test_color_picker_instantiates(self, qapp):
        from cortex_portfolio.editor.game_def_forms import ColorPicker
        ColorPicker()

    def test_game_form_instantiates(self, qapp):
        from cortex_portfolio.editor.game_def_forms import GameForm
        GameForm()

    def test_prime_set_form_instantiates(self, qapp):
        from cortex_portfolio.editor.game_def_forms import PrimeSetForm
        PrimeSetForm()

    def test_extras_form_instantiates(self, qapp):
        from cortex_portfolio.editor.game_def_forms import ExtrasForm
        ExtrasForm()

    def test_actor_type_form_instantiates(self, qapp):
        from cortex_portfolio.editor.game_def_forms import ActorTypeForm
        ActorTypeForm("character")


class TestSectionEditors:
    def test_identity_editor_instantiates(self, qapp):
        from cortex_portfolio.editor.section_editors import IdentityEditor
        IdentityEditor()

    def test_portrait_picker_instantiates(self, qapp):
        from cortex_portfolio.editor.section_editors import PortraitPicker
        PortraitPicker()

    def test_growth_editor_instantiates(self, qapp):
        from cortex_portfolio.editor.section_editors import GrowthEditor
        GrowthEditor()

    def test_complications_editor_instantiates(self, qapp):
        from cortex_portfolio.editor.section_editors import ComplicationsEditor
        ComplicationsEditor()

    def test_sessions_editor_instantiates(self, qapp):
        from cortex_portfolio.editor.section_editors import SessionsEditor
        SessionsEditor()

    def test_notes_editor_instantiates(self, qapp):
        from cortex_portfolio.editor.section_editors import NotesEditor
        NotesEditor()

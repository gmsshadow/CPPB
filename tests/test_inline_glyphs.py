"""Tests for the inline-glyphs token expansion filter.

The contract:
  - {pp}, {xp}, {d4}..{d12} get replaced with HTML
  - case-insensitive
  - unknown tokens left alone (rendered as literal "{foo}")
  - empty/None input handled cleanly
  - non-token text is HTML-escaped (no XSS through the filter)
"""
from cortex_portfolio.render import inline_glyphs


class TestInlineGlyphs:
    def test_empty_input_renders_nothing(self):
        assert str(inline_glyphs("")) == ""
        assert str(inline_glyphs(None)) == ""

    def test_plain_text_passes_through_escaped(self):
        # No tokens, but the text contains HTML-significant characters
        # that must be escaped (this filter declares its output safe so
        # it's our responsibility to escape).
        result = str(inline_glyphs("a < b & c > d"))
        assert "<" not in result
        assert "&" in result   # escaped form
        assert "a " in result and " b " in result

    def test_pp_token_renders_pill(self):
        out = str(inline_glyphs("spend {pp} to act"))
        assert "pp-pill" in out
        assert ">PP<" in out
        assert "spend " in out
        assert " to act" in out

    def test_xp_token_renders_xp_pill(self):
        out = str(inline_glyphs("earn 3 {xp} this session"))
        assert "xp-pill" in out
        assert ">XP<" in out

    def test_dice_token_renders_die_span(self):
        out = str(inline_glyphs("roll a {d8} for the attack"))
        assert 'class="die die--inline"' in out
        assert 'data-rating="d8"' in out

    def test_all_die_sizes_recognized(self):
        for size in ("d4", "d6", "d8", "d10", "d12"):
            out = str(inline_glyphs(f"have a {{{size}}}"))
            assert f'data-rating="{size}"' in out, f"missed {size}"

    def test_tokens_are_case_insensitive(self):
        for variant in ("{PP}", "{pp}", "{Pp}", "{pP}"):
            assert "pp-pill" in str(inline_glyphs(variant))
        for variant in ("{D8}", "{d8}", "{D8}"):
            assert 'data-rating="d8"' in str(inline_glyphs(variant))

    def test_unknown_tokens_pass_through_escaped(self):
        # An unknown token should render as literal "{foo}" in the PDF,
        # not become a substitution and not break the layout.
        out = str(inline_glyphs("see {ref} for details"))
        # The literal braces survive (possibly escaped).
        assert "{ref}" in out or "&#123;ref&#125;" in out or "&#x7B;ref&#x7D;" in out
        # And nothing matching a glyph class got introduced.
        assert "pp-pill" not in out
        assert 'class="die' not in out

    def test_multiple_tokens_in_one_string(self):
        out = str(inline_glyphs("spend {pp} for a {d6}, gain {xp}"))
        assert "pp-pill" in out
        assert "xp-pill" in out
        assert 'data-rating="d6"' in out

    def test_d20_is_unknown_token(self):
        # We don't recognize d20 (not a Cortex die) -- should pass through.
        out = str(inline_glyphs("roll a {d20}"))
        # The exact textual form depends on escape but the marker must not
        # become a styled die.
        assert "die--inline" not in out

    def test_text_outside_tokens_is_escaped(self):
        # XSS safety: an author who pastes "<script>" should not get
        # script execution.
        out = str(inline_glyphs("dangerous: <script>x</script>"))
        assert "<script>" not in out

    def test_braces_without_match_pass_through(self):
        # A stray "{" or "}" or "{ a b }" (whitespace inside) should not
        # crash and should leave the text essentially intact.
        out = str(inline_glyphs("see equation {a + b}"))
        # No substitution because the inside isn't [A-Za-z0-9]+
        assert "die--inline" not in out
        assert "pp-pill" not in out

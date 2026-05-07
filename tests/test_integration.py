"""End-to-end integration tests: real PDF generation and CLI exit codes."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cortex_portfolio.render import render_pdf


# ---------------------------------------------------------------------------
# render_pdf: the headline integration test. If this passes, the whole
# JSON -> Jinja -> WeasyPrint -> PDF pipeline is working.
# ---------------------------------------------------------------------------

class TestRenderPDF:
    def test_produces_a_pdf(self, tmp_path, examples_dir):
        out = tmp_path / "test.pdf"
        result = render_pdf(
            examples_dir / "hammerheads.game.json",
            examples_dir / "reyes.character.json",
            out,
        )
        assert result == out
        assert out.is_file()
        # PDF magic bytes -- "%PDF-" at the start.
        assert out.read_bytes().startswith(b"%PDF-")

    def test_renders_each_bundled_pairing(self, tmp_path, examples_dir):
        cases = [
            ("hammerheads.game.json", "reyes.character.json"),
            ("hammerheads.game.json", "black_sea.character.json"),
            ("vigilant.game.json",    "harker.character.json"),
        ]
        for game, char in cases:
            out = tmp_path / f"{Path(char).stem}.pdf"
            render_pdf(examples_dir / game, examples_dir / char, out)
            assert out.read_bytes().startswith(b"%PDF-")
            # Reasonable size sanity-check: under 1KB means the PDF is empty.
            assert out.stat().st_size > 1024


# ---------------------------------------------------------------------------
# CLI: validates argparse wiring, exit codes, and end-to-end install.
# Uses subprocess so it reflects the real entry point installed by pip.
# ---------------------------------------------------------------------------

def _run_cli(*args: str | Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cortex_portfolio", *map(str, args)],
        capture_output=True, text=True,
    )


class TestCLI:
    def test_check_succeeds_on_valid_data(self, examples_dir):
        result = _run_cli(
            "--check",
            examples_dir / "hammerheads.game.json",
            examples_dir / "reyes.character.json",
        )
        assert result.returncode == 0

    def test_check_with_only_game_def(self, examples_dir):
        result = _run_cli("--check", examples_dir / "hammerheads.game.json")
        assert result.returncode == 0

    def test_unknown_actor_type_exits_nonzero(self, tmp_path, examples_dir):
        bad = tmp_path / "bad.character.json"
        bad.write_text(
            '{"actor_type": "not-a-real-type", "prime_sets": {}}',
            encoding="utf-8",
        )
        result = _run_cli(
            "--check",
            examples_dir / "hammerheads.game.json",
            bad,
        )
        assert result.returncode != 0
        assert "actor_type" in result.stderr

    def test_strict_promotes_warnings_to_blocking(self, tmp_path, examples_dir):
        # A character with a v1-shape die string -> warning, not error.
        warned = tmp_path / "warned.character.json"
        warned.write_text(
            '{"actor_type": "character", "prime_sets": {'
            '"distinctions": [{"name": "X", "dice": "d8"}, '
            '{"name": "Y", "dice": ["d8"]}, {"name": "Z", "dice": ["d8"]}]'
            '}}',
            encoding="utf-8",
        )
        # No --strict: passes (warning only).
        ok = _run_cli("--check", examples_dir / "hammerheads.game.json", warned)
        assert ok.returncode == 0
        # With --strict: fails because warnings now block.
        strict = _run_cli(
            "--strict", "--check",
            examples_dir / "hammerheads.game.json", warned,
        )
        assert strict.returncode != 0

    def test_render_writes_pdf(self, tmp_path, examples_dir):
        out = tmp_path / "out.pdf"
        result = _run_cli(
            examples_dir / "hammerheads.game.json",
            examples_dir / "reyes.character.json",
            out,
        )
        assert result.returncode == 0
        assert out.is_file()
        assert out.stat().st_size > 1024

    def test_malformed_json_reports_clean_error(self, tmp_path, examples_dir):
        bad = tmp_path / "broken.json"
        bad.write_text("{ this is not valid json", encoding="utf-8")
        result = _run_cli("--check", bad)
        assert result.returncode != 0
        assert "invalid JSON" in result.stderr

    def test_missing_file_reports_clean_error(self, tmp_path):
        result = _run_cli("--check", tmp_path / "does-not-exist.json")
        assert result.returncode != 0
        assert "not found" in result.stderr

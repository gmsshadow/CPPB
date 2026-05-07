"""Command-line entry point.

Usage:
    cortex-portfolio GAME.json CHARACTER.json OUT.pdf       # validate + render
    cortex-portfolio --check GAME.json [CHARACTER.json]     # validate only
    cortex-portfolio --strict ... ...                       # warnings -> errors
"""
from __future__ import annotations

# Silence the GLib-GIO warnings WeasyPrint's GTK runtime emits on Windows
# during startup (it enumerates UWP app file associations, which on modern
# Windows 11 produces dozens of "supports N extensions but has no verbs"
# messages). These must be set before WeasyPrint imports anything from the
# GTK stack -- so they belong at the very top of this module, ahead of the
# render import below.
import os as _os
_os.environ.setdefault("GIO_USE_VFS", "local")
_os.environ.setdefault("G_MESSAGES_DEBUG", "")

import argparse
import json
import sys
from pathlib import Path

from .render import render_pdf
from .validate import validate, split


def _print_issues(issues: list, *, file=sys.stderr) -> None:
    if not issues:
        return
    errs, warns = split(issues)
    for i in errs:
        print(i, file=file)
    for i in warns:
        print(i, file=file)
    print(f"\n{len(errs)} error(s), {len(warns)} warning(s)", file=file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cortex-portfolio",
        description="Render a Cortex Prime character to a PDF portfolio.",
    )
    parser.add_argument("game",      type=Path, help="Path to the game definition JSON.")
    parser.add_argument("character", type=Path, nargs="?",
                        help="Path to the character JSON. Required unless --check is used alone.")
    parser.add_argument("output",    type=Path, nargs="?",
                        help="Path to write the PDF to. Required unless --check is used.")
    parser.add_argument("--check", action="store_true",
                        help="Validate inputs and report issues; do not render.")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors.")
    args = parser.parse_args(argv)

    # ----- Load --------------------------------------------------------
    if not args.game.is_file():
        print(f"error: file not found: {args.game}", file=sys.stderr)
        return 2
    try:
        game = json.loads(args.game.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: {args.game}: invalid JSON: {e}", file=sys.stderr)
        return 2

    character = None
    if args.character is not None:
        if not args.character.is_file():
            print(f"error: file not found: {args.character}", file=sys.stderr)
            return 2
        try:
            character = json.loads(args.character.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"error: {args.character}: invalid JSON: {e}", file=sys.stderr)
            return 2

    # ----- Validate ----------------------------------------------------
    issues = validate(game, character)
    _print_issues(issues)
    errs, warns = split(issues)
    blocking = bool(errs) or (args.strict and bool(warns))

    # ----- Check-only mode --------------------------------------------
    if args.check:
        if not issues:
            print("OK: no issues.", file=sys.stderr)
        return 1 if blocking else 0

    # ----- Render mode requires character + output --------------------
    if args.character is None or args.output is None:
        parser.error("character and output are required unless --check is set")

    if blocking:
        print("aborting render due to validation issues "
              f"({'use --check to inspect' if errs else 'remove --strict to allow warnings'})",
              file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out = render_pdf(args.game, args.character, args.output)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

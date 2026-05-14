# Cortex Portfolio

Data-driven PDF generator for Cortex Prime character sheets.
A character + a game definition (both JSON) → a printable PDF.

```
game.json  ─┐
            ├──► render.py (Jinja2 + WeasyPrint) ──► sheet.pdf
character.json
                    ▲
                    └─ assets/templates/{sheet.html.j2, sheet.css}
                    └─ assets/fonts/{cortex-icons, fa-solid, fa-regular}
```

The **game definition** declares which Prime Sets are in play (Distinctions,
Attributes, Skills, Values, Power Sets, ...) — and what dice / counts /
icons / capability flags each uses. The **character file** fills in the
values. The renderer iterates `prime_sets` in definition order and only
renders sections the character actually has data for.

## Install (developers)

```bash
git clone <repo>
cd cortex-portfolio
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -e ".[dev]"            # editable install + test/build tools
```

The editable install gives you a `cortex-portfolio` command on `$PATH`.

## Run

A PyQt6-based desktop editor is included for editing characters without
touching JSON:

```bash
pip install -e ".[editor]"     # pulls in PyQt6 alongside the dev install
cortex-portfolio-editor
```

The editor is a three-pane application: section list on the left, current
section's form in the middle, live validation on the right. Trait-form
inputs are driven entirely by the same capability flags (`has_label`,
`has_dice`, `has_sub_traits`, ...) the renderer reads, so a new game preset
gets editor support with **zero editor code changes**. Render via the
Render menu (Ctrl+R).

Render a character from the CLI:

```bash
cortex-portfolio examples/hammerheads.game.json \
                 examples/reyes.character.json \
                 out/reyes.pdf
```

Validate without rendering (catches typos, schema drift, dice not in pool,
unknown actor types, etc.):

```bash
cortex-portfolio --check examples/hammerheads.game.json examples/reyes.character.json

# game definition alone
cortex-portfolio --check examples/hammerheads.game.json

# treat warnings as errors
cortex-portfolio --strict examples/hammerheads.game.json examples/reyes.character.json out/reyes.pdf
```

Validation runs automatically before every render — fatal errors block,
warnings don't (unless `--strict`).

## Test

```bash
pytest                       # all 49 tests, ~15s
pytest -k validate           # just the validator suite
pytest tests/test_integration.py -v
```

## Build a Windows executable

A PyInstaller spec is included that bundles fonts, templates, WeasyPrint,
and the Python runtime into a single `.exe` you can hand to a friend who
has no Python installed.

### Prerequisite: install GTK runtime

WeasyPrint on Windows depends on the GTK runtime libraries (Pango, Cairo,
GLib). They're not bundled with WeasyPrint itself; you need to install
them once on the build machine. PyInstaller then packs them into the
resulting `.exe`, so end users of the bundle don't need GTK themselves.

The simplest way:

1. Download the latest `gtk3-runtime-*-ts-win64.exe` from
   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
2. Run the installer. **Keep "Set up PATH environment variable to include
   GTK+" enabled.** Default install location is
   `C:\Program Files\GTK3-Runtime Win64\` — the PyInstaller spec already
   knows to look there.
3. Open a fresh PowerShell so the new PATH applies, then verify:

   ```powershell
   python -m weasyprint --info
   ```

   You should see version info including a `Pango version:` line.

### Building the CLI

From a fresh checkout, in PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pyinstaller cortex-portfolio.spec --clean
```

Output is `dist\cortex-portfolio.exe`. Test with:

```powershell
.\dist\cortex-portfolio.exe examples\hammerheads.game.json `
                            examples\reyes.character.json `
                            out\reyes.pdf
```

The executable is around 50–80 MB — Python runtime, WeasyPrint, GTK, and
all dependencies bundled in. The resulting `.exe` is self-contained;
end users do **not** need GTK installed to run it.

### Building the editor

The editor's bundle is a separate spec because it adds PyQt6 (the GUI
toolkit) on top of everything the CLI bundles. The build needs the
`editor` extra installed:

```powershell
pip install -e ".[dev,editor]"            # NOT just [dev] -- see below
pyinstaller cortex-portfolio-editor.spec --clean
```

Output is `dist\cortex-portfolio-editor.exe`, around 130–160 MB. Test with:

```powershell
.\dist\cortex-portfolio-editor.exe
```

The editor window should appear with no console window alongside it.

> ⚠️ **The `[editor]` extra is required for the build, not just for running
> from source.** PyInstaller only bundles what's importable in *its*
> environment. If you build the editor spec without PyQt6 installed, the
> .exe will be smaller (no Qt runtime included) but will crash at launch
> with `ModuleNotFoundError: No module named 'PyQt6'`. See the
> Troubleshooting section below.

### Note about console output

The bundled .exe (and `python -m weasyprint --info`) emits a few
`GLib-GIO-WARNING` lines on first startup as GLib enumerates Windows app
file associations. These are cosmetic and silenced inside the program by
`cli.py` setting `GIO_USE_VFS=local` — but if you run WeasyPrint
directly outside this project's CLI, you'll see them.

## Adding a new game preset

1. Copy `examples/hammerheads.game.json` to a new file.
2. Edit the `actor_types` map: each actor type (Character, Scene, Ship, …)
   has its own `prime_sets` list and `extras` block.
3. Each prime set's `settings` flags drive rendering:
   - `has_label` / `has_dice` / `has_description` / `has_statement`
   - `has_sfx` / `has_limits` / `has_sub_traits`
   - `sub_traits_label` / `sub_traits_have_dice` / `sub_traits_dice`
4. Validate with `cortex-portfolio --check your.game.json`.
5. Add example characters and validate them too.

For non-trivial games, take a look at:

- `examples/hammerheads.game.json` — naval aviators, two actor types
  (Character + Scene), Doom Pool, classic 5-prime-set character.
- `examples/vigilant.game.json` — modern occult investigation, exercises
  Power Sets (description + sub-traits + SFX + Limits, no top-level die).
- `examples/xadia.game.json` — Tales of Xadia preset, contributed by a
  user who built it through the editor; demonstrates a 7-prime-set
  character (Distinctions, Attributes, Values, Specialities, Assets,
  Relationships, Goals) with six stress tracks. The Timba example
  character uses the first five.

### Character portraits

A character can carry an optional portrait, embedded directly in the
character JSON as a base64 data URI under `identity.portrait`. The editor
handles the load and encode flow: pick an image from disk, it gets
downscaled to fit within 600×600 and re-encoded as JPEG quality 80, then
stored in the JSON. Typical portrait adds 20–40 KB to the character file.

When set, the portrait renders as a small square at the top-right of the
sheet header. When absent, the header reflows naturally — no empty space.

The portrait field is a string; the editor produces data URIs, but the
renderer will pass any string through to `<img src="…">`. So external
URLs work too, with the caveat that they won't embed in offline PDFs
(the validator warns about this).

### XP track

An optional Hammerheads-style XP track: a vertical column of fillable
circles ("pips") down the right margin of page 1. Enable it per actor
type:

```json
"extras": {
  "xp_track": { "enabled": true, "pips": 17, "label": "XP" }
}
```

`pips` defaults to 17 (the Hammerheads count); `label` defaults to "XP".
It is pure worksheet scaffolding — there is no per-character XP value,
players just pencil in the circles during play, the same approach as the
writable PP box.

The track is page-1 only. Page 1's right margin widens to make room;
later pages keep the full content width.

### Alternative XP systems

Cortex games use one of several XP/advancement systems. The schema
supports two so far, declared per actor type under `extras`:

- **Milestones** — three-tiered triggers (`1xp` / `3xp` / `10xp`) per
  milestone. Use when the game leans on named milestones with explicit
  triggers (Hammerheads, Marvel Heroic, Smallville).
- **Growth Pool** — a free-form list of `{die, text}` entries the player
  fills in as awards are earned during play. Use when the game tracks
  XP as die-rated awards rather than tiered milestones (Tales of Xadia).

Enable one or the other in the game-def:

```json
"extras": { "growth": { "enabled": true } }
```

Records on the character side are just a list:

```json
"extras": {
  "growth": [
    { "die": "d6", "text": "Saved the village from the experiment" }
  ]
}
```

Enabling both produces a validator warning: canonical Cortex treats them
as alternatives. Some homebrew uses both; you can ignore the warning if
that's intentional.

## Adding a new icon

Game definitions reference Font Awesome icons by name (`"icon": "scroll"`).
To use a new icon, add the codepoint to `FA_ICONS` in `render.py`.
Codepoints are listed in the official cheatsheet at
fontawesome.com/v5/cheatsheet/free/solid.

## Logs

Every run of the CLI or editor writes a timestamped log file to a
per-user folder, capturing everything that went to stdout/stderr plus
any uncaught Python exceptions. This is what makes the bundled `.exe`
debuggable when launched from Explorer (no console attached).

Locations:

- **Windows:** `%LOCALAPPDATA%\CortexPortfolio\logs\`
- **macOS:** `~/Library/Logs/CortexPortfolio/`
- **Linux:** `$XDG_STATE_HOME/CortexPortfolio/logs/` (defaults to `~/.local/state/CortexPortfolio/logs/`)

The editor exposes this folder via **Help → Open Log Folder**. If the
app crashes or behaves oddly, the most recent log in there is the
single most useful thing to attach when asking for help.

Only the 10 most recent log files are kept; older ones get pruned at
each startup so the folder doesn't accumulate forever.

## Troubleshooting

### `OSError: cannot load library 'libgobject-2.0-0'` on Windows

WeasyPrint can't find GTK. Install the GTK3 runtime
(see "Build a Windows executable" → "Prerequisite: install GTK runtime")
and reopen PowerShell so the new PATH applies. Verify with
`python -m weasyprint --info` — you should see a `Pango version:` line.

### Editor `.exe` crashes with `ModuleNotFoundError: No module named 'PyQt6'`

The build environment didn't have PyQt6 installed. PyInstaller can only
bundle what's importable in its own venv, so building the editor spec
with only `pip install -e ".[dev]"` produces a bundle with no Qt runtime
inside.

Fix:

```powershell
pip install -e ".[dev,editor]"
pyinstaller cortex-portfolio-editor.spec --clean
```

You can verify before rebuilding that the venv has the right packages:

```powershell
pip show PyQt6
```

If the path it prints is *not* under your project's `venv\` directory,
you're picking up a system Python install — re-activate your venv with
`venv\Scripts\Activate.ps1` and reinstall.

The same lesson generalizes: **if `python -m cortex_portfolio.editor`
works from source but the bundled .exe fails with `ModuleNotFoundError`,
suspect a missing extra in the install used for the build.**

### GLib-GIO-WARNING lines on startup

These come from GLib enumerating Windows app file associations during
its initialization. They're cosmetic and never indicate a real problem.

The PyInstaller spec files wire in a runtime hook
(`_pyinstaller_rthook_silence_glib.py`) that sets `GIO_USE_VFS=local`
and `G_MESSAGES_DEBUG=""` before any bundled DLL loads — that suppresses
the warnings in the bundled `.exe`. If you still see them after a build,
confirm the spec's `runtime_hooks=[...]` argument references the hook
file and rebuild with `--clean`.

When running from source (`python -m cortex_portfolio.editor`), the
same env vars get set at the top of `cli.py` / `editor/__main__.py`,
which is good enough for the non-bundled case.

### Editor window doesn't appear (no error, no window)

Most likely: PyQt6's Windows platform plugin (`qwindows.dll`) wasn't
bundled by PyInstaller's hook. Run from PowerShell rather than
double-clicking — Qt prints a useful error to stdout in this case
("This application failed to start because no Qt platform plugin
could be initialized"). If you see that, try rebuilding with an
explicit collect-all in the spec:

In `cortex-portfolio-editor.spec`, change:

```python
hiddenimports = collect_submodules("weasyprint")
```

to:

```python
from PyInstaller.utils.hooks import collect_all
hiddenimports = collect_submodules("weasyprint")
qt_datas, qt_binaries, qt_hiddenimports = collect_all("PyQt6")
datas += qt_datas
hiddenimports += qt_hiddenimports
```

and add `qt_binaries` to the `binaries=[]` argument of `Analysis(...)`.

## Inline glyphs in text

Free-text fields (SFX, Limits, descriptions, statements, notes, growth
entries, milestone tier text, session notes, concept subtitle) recognize
a handful of inline token markers that render as styled glyphs:

| Token | Renders as |
|---|---|
| `{pp}` | maroon **PP** pill |
| `{xp}` | muted **XP** pill |
| `{d4}` through `{d12}` | inline die glyph at the matching rating |

Example SFX text:

```
Spend a {pp} to step up Dark Magic for one roll. Roll an extra {d8}
with the attack pool. Gain {xp} when the cost catches up with you.
```

Tokens are case-insensitive (`{PP}`, `{pp}`, `{Pp}` all work). Unknown
tokens like `{ref}` pass through as literal text — no false-positive
substitution. To produce a literal `{pp}` in text without substitution,
use any unknown token form (e.g. `{pp_literal}`) — there's no escape
syntax because the practical need hasn't come up.

## Project layout

```
cortex_portfolio/
├── pyproject.toml
├── cortex-portfolio.spec        # PyInstaller config (CLI)
├── cortex-portfolio-editor.spec # PyInstaller config (GUI)
├── README.md
├── examples/
│   ├── hammerheads.game.json
│   ├── vigilant.game.json
│   ├── xadia.game.json
│   ├── reyes.character.json     (Character actor type)
│   ├── black_sea.character.json (Scene actor type)
│   ├── harker.character.json    (Power-Set-using investigator)
│   ├── timba.character.json     (Tales of Xadia)
│   └── broken.character.json    (intentionally invalid; validator demo)
├── src/cortex_portfolio/
│   ├── __init__.py              # version + DIE_DIGIT constants
│   ├── __main__.py              # python -m entry
│   ├── cli.py                   # argparse front-end
│   ├── render.py                # JSON -> rows -> Jinja -> WeasyPrint -> PDF
│   ├── validate.py              # schema + cross-validation
│   ├── editor/                  # PyQt6 desktop editor
│   │   ├── __main__.py
│   │   ├── main_window.py       # character editor
│   │   ├── trait_form.py        # flag-driven trait widget
│   │   ├── section_editors.py   # identity / stress / milestones / etc.
│   │   ├── section_list.py      # left-pane navigator
│   │   ├── issues_panel.py      # right-pane validation feedback
│   │   ├── game_def_window.py   # game-definition editor
│   │   ├── game_def_forms.py    # game-def form widgets
│   │   └── widgets.py           # shared dice/icon/list editors
│   └── assets/
│       ├── fonts/               # cortex-icons + Font Awesome
│       └── templates/
│           ├── sheet.html.j2
│           └── sheet.css
└── tests/
    ├── conftest.py             # fixtures pointing at examples/
    ├── test_validate.py        # validator unit tests
    ├── test_render.py          # dice/icon/layout helpers
    └── test_integration.py     # full pipeline + CLI smoke tests
```

## Credits

Dice and icon fonts from the Cortex Community Assets (CC BY 4.0).
Font Awesome 5 Free icons (CC BY 4.0).

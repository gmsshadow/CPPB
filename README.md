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

### Building

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

## Adding a new icon

Game definitions reference Font Awesome icons by name (`"icon": "scroll"`).
To use a new icon, add the codepoint to `FA_ICONS` in `render.py`.
Codepoints are listed in the official cheatsheet at
fontawesome.com/v5/cheatsheet/free/solid.

## Project layout

```
cortex_portfolio/
├── pyproject.toml
├── cortex-portfolio.spec       # PyInstaller config
├── README.md
├── examples/
│   ├── hammerheads.game.json
│   ├── vigilant.game.json
│   ├── reyes.character.json    (Character actor type)
│   ├── black_sea.character.json (Scene actor type)
│   ├── harker.character.json   (Power-Set-using investigator)
│   └── broken.character.json   (intentionally invalid; for the validator demo)
├── src/cortex_portfolio/
│   ├── __init__.py             # version + DIE_DIGIT constants
│   ├── __main__.py             # python -m entry
│   ├── cli.py                  # argparse front-end
│   ├── render.py               # JSON -> rows -> Jinja -> WeasyPrint -> PDF
│   ├── validate.py             # schema + cross-validation
│   └── assets/
│       ├── fonts/              # cortex-icons + Font Awesome
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

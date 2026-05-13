# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Cortex Portfolio.

Build (from a checkout, with `pip install -e .[dev]` first):

    pyinstaller cortex-portfolio.spec --clean

Outputs:
    dist/cortex-portfolio.exe   (Windows, single-file)
    dist/cortex-portfolio       (Linux/macOS, single-file)

Notes:
- WeasyPrint pulls a number of pure-Python dependencies (pydyf, tinycss2,
  cssselect2, html5lib, pyphen, fonttools, pillow). PyInstaller picks these
  up via dependency analysis; if a fresh upstream release adds new dynamic
  imports we may need to add them to `hiddenimports` here.
- On Windows, WeasyPrint 53+ does NOT need a system GTK install; fonts and
  font-config come from packaged libraries via the wheel.
- `assets/` is bundled as data because the renderer reads templates and
  fonts from disk at runtime.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Bundle the package's assets (fonts + templates). PyInstaller materializes
# these at runtime under sys._MEIPASS, which assets_dir() in render.py
# already detects.
datas  = collect_data_files("cortex_portfolio", includes=["assets/**/*"])

# WeasyPrint ships small pure-Python data files (default UA stylesheet,
# pattern files). Collecting them defensively keeps PDF generation working
# across versions.
datas += collect_data_files("weasyprint")
datas += collect_data_files("tinycss2")
datas += collect_data_files("cssselect2")
datas += collect_data_files("pyphen")

# Some WeasyPrint internals are imported by string. Add anything that
# turns out to be missing once you actually run the bundle.
hiddenimports = [
    *collect_submodules("weasyprint"),
    "PIL.Image",
    "PIL.ImageOps",
]

a = Analysis(
    ["src/cortex_portfolio/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["_pyinstaller_rthook_silence_glib.py"],
    excludes=[
        "tkinter",        # not used; saves ~3 MB on Windows
        "pytest",
        "pyinstaller",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="cortex-portfolio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # safe; if it ever causes issues on Windows, set False
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # CLI tool: keep the console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

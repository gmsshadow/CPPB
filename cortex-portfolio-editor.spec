# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Cortex Portfolio Editor.

Build (from a checkout, with `pip install -e ".[dev,editor]"` first, plus
GTK runtime installed -- see README):

    pyinstaller cortex-portfolio-editor.spec --clean

Outputs:
    dist/cortex-portfolio-editor.exe   (Windows, single-file, GUI)

Notes:
- This is the GUI counterpart to cortex-portfolio.spec. Same WeasyPrint
  dependency story, plus PyQt6 on top.
- console=False so the editor doesn't open a terminal alongside its window.
  Tracebacks from uncaught exceptions become Windows error dialogs, which
  is the right behavior for end users (they can screenshot and send).
- The bundle is large (~130-160 MB on Windows) because PyQt6's Qt runtime
  ships in full. That's expected for any PyQt6 PyInstaller build.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Data files: same as the CLI build plus PyQt6 plugins/translations.
datas  = collect_data_files("cortex_portfolio", includes=["assets/**/*"])
datas += collect_data_files("weasyprint")
datas += collect_data_files("tinycss2")
datas += collect_data_files("cssselect2")
datas += collect_data_files("pyphen")

# WeasyPrint internals are sometimes imported by string.
hiddenimports  = collect_submodules("weasyprint")
hiddenimports += [
    "PIL.Image",
    "PIL.ImageOps",
]

a = Analysis(
    ["src/cortex_portfolio/editor/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",         # not used; saves a few MB
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
    name="cortex-portfolio-editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # GUI app -- no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

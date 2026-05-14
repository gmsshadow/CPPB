"""Guard: PyInstaller entry-point modules must use only absolute imports.

Background: a module run as `__main__` (which is how PyInstaller invokes
the bundled entry point) has no parent package, so any relative import
(`from . import x`, `from .. import y`) fails at runtime with:

    ImportError: attempted relative import with no known parent package

This has bitten the project three times -- each time in an entry-point
__main__.py, each time only discovered when the built .exe crashed on a
user's machine. The regular test suite never catches it because tests
import these modules *through the package*, which gives them the parent
context that PyInstaller's invocation doesn't.

This test parses the entry-point files with `ast` and fails if any of
them contains a relative import. It's a static check -- no Qt, no
subprocess, no build -- so it runs fast and catches the bug at commit
time instead of post-distribution.

If you add a new PyInstaller entry point, add it to ENTRY_POINTS below.
"""
import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src" / "cortex_portfolio"

# Every module that PyInstaller runs directly as __main__. These are the
# `Analysis([...])` script paths in the .spec files.
ENTRY_POINTS = [
    _SRC / "__main__.py",
    _SRC / "editor" / "__main__.py",
]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=lambda p: str(p.relative_to(_SRC)))
def test_entry_point_has_no_relative_imports(entry_point):
    """Entry-point modules must import everything absolutely."""
    assert entry_point.exists(), f"entry point missing: {entry_point}"

    tree = ast.parse(entry_point.read_text(encoding="utf-8"), filename=str(entry_point))

    offenders = []
    for node in ast.walk(tree):
        # ImportFrom.level: 0 = absolute, 1 = `from .`, 2 = `from ..`, etc.
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            dots = "." * node.level
            mod = node.module or ""
            offenders.append(f"  line {node.lineno}: from {dots}{mod} import ...")

    assert not offenders, (
        f"{entry_point.relative_to(_SRC)} uses relative imports, which break "
        f"when PyInstaller runs it as __main__:\n" + "\n".join(offenders) +
        "\n\nUse absolute imports (from cortex_portfolio... import ...) instead."
    )


def test_entry_points_list_is_current():
    """Sanity check: every __main__.py under src/ is in ENTRY_POINTS.

    If someone adds a new entry point and forgets to register it here,
    this fails -- so the relative-import guard above can't silently miss
    a new entry point.
    """
    found = set(_SRC.rglob("__main__.py"))
    registered = set(ENTRY_POINTS)
    missing = found - registered
    assert not missing, (
        "Found __main__.py files not registered in ENTRY_POINTS:\n" +
        "\n".join(f"  {p.relative_to(_SRC)}" for p in sorted(missing)) +
        "\n\nAdd them so the relative-import guard covers them too."
    )

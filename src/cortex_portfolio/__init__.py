"""Cortex Prime character portfolio generator."""
__version__ = "0.0.2"

# Canonical mapping of die rating -> the digit character that the cortex-icons
# font renders as the corresponding polyhedron. Lives here (not in render.py)
# so the validator can import it without pulling WeasyPrint in transitively.
DIE_DIGIT = {"d4": "4", "d6": "6", "d8": "8", "d10": "0", "d12": "2"}
VALID_DICE = frozenset(DIE_DIGIT.keys())

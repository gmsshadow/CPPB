"""PDF rendering pipeline for Cortex character portfolios.

Pipeline: game_definition.json + character.json
        -> Jinja2 template (sheet.html.j2)
        -> WeasyPrint (HTML + CSS + embedded fonts)
        -> sheet.pdf
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from weasyprint import HTML

from . import DIE_DIGIT


# ---------------------------------------------------------------------------
# Asset path resolution. Works both from source (Path(__file__)) and from
# inside a PyInstaller bundle (sys._MEIPASS holds the extraction directory).
# ---------------------------------------------------------------------------

def assets_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "cortex_portfolio" / "assets"
    return Path(__file__).resolve().parent / "assets"


# ---------------------------------------------------------------------------
# Cortex dice icons. Each die rating maps to one digit character which the
# cortex-icons font renders as the complete polyhedron with its number drawn
# inside. The leading "d" is stripped and only the LAST char is needed.
# DIE_DIGIT is defined in __init__.py so the validator can use it too.
# ---------------------------------------------------------------------------


def _coerce_dice(value: str | list[str] | None) -> list[str]:
    """Accept either a single die string or a list; return a clean list.
    Tolerates the old single-die schema for forward compatibility."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def dice_icons(value: str | list[str] | None) -> Markup:
    """Render dice (one or many) as a row of HTML spans using the cortex-icons font."""
    dice = _coerce_dice(value)
    if not dice:
        return Markup('<span class="die die--empty">\u2014</span>')

    parts: list[str] = []
    for rating in dice:
        digit = DIE_DIGIT.get(rating)
        if digit is None:
            parts.append(f'<span class="die die--unknown">{rating}</span>')
        else:
            parts.append(f'<span class="die" data-rating="{rating}">{digit}</span>')
    return Markup("".join(parts))


# ---------------------------------------------------------------------------
# Font Awesome icon name -> codepoint. Expand as new game definitions need
# more icons. Codepoints from fontawesome.com/v5/cheatsheet/free/solid.
# ---------------------------------------------------------------------------

FA_ICONS = {
    # Section / prime-set icons
    "scroll":      "\uf70e",
    "user":        "\uf007",
    "user-circle": "\uf2bd",
    "bullseye":    "\uf140",
    "heart":       "\uf004",
    "crosshairs":  "\uf05b",
    "shield-alt":  "\uf3ed",
    "medal":       "\uf5a2",
    "coins":       "\uf51e",
    "book-open":   "\uf518",
    "bolt":        "\uf0e7",
    "ban":         "\uf05e",
    "crown":       "\uf521",
    "skull":       "\uf54c",
    "dragon":      "\uf6d5",
    "hat-wizard":  "\uf6e8",
    "hammer":      "\uf6e3",
}


def icon_glyph(name: str | None) -> Markup:
    """Return the HTML-safe unicode glyph for a named Font Awesome icon."""
    if not name:
        return Markup("")
    cp = FA_ICONS.get(name)
    if cp is None:
        return Markup(f'<!-- unknown icon: {name} -->')
    return Markup(cp)


# ---------------------------------------------------------------------------
# Actor type resolution. The game definition contains an `actor_types` map
# keyed by id (e.g. "character", "scene", "ship"). The character file picks
# one via its `actor_type` field (defaults to "character").
#
# Backwards-compat shim: if the game definition has top-level `prime_sets`
# (the v1 shape), wrap it into a synthetic single "character" actor type.
# ---------------------------------------------------------------------------

def resolve_actor_type(game_def: dict, actor_type_id: str | None) -> dict:
    actor_type_id = actor_type_id or "character"

    if "actor_types" in game_def:
        if actor_type_id not in game_def["actor_types"]:
            available = ", ".join(sorted(game_def["actor_types"].keys()))
            raise ValueError(
                f"Unknown actor type {actor_type_id!r}; "
                f"game definition has: {available}"
            )
        return game_def["actor_types"][actor_type_id]

    # v1 compat: top-level prime_sets / extras become a single character type
    return {
        "label": "Character",
        "prime_sets": game_def.get("prime_sets", []),
        "extras": game_def.get("extras", {}),
    }


# ---------------------------------------------------------------------------
# Layout: build a sequence of rows. Each row is a list of 1 or 2 section
# descriptors. Half-width sections pair up; full-width sections stand alone.
# Rows render as independent block-level flex containers, which lets
# WeasyPrint page-break between them cleanly.
# ---------------------------------------------------------------------------

# Heuristic: a prime set goes full-width if it has more than this many entries
# OR if any entry has sub-traits (because sub-traits add vertical bulk).
_FULL_WIDTH_TRAIT_THRESHOLD = 4


def _is_wide_prime_set(prime_set_def: dict, entries: list[dict]) -> bool:
    if len(entries) > _FULL_WIDTH_TRAIT_THRESHOLD:
        return True
    settings = prime_set_def.get("settings", {})
    if settings.get("has_sub_traits"):
        if any(e.get("sub_traits") for e in entries):
            return True
    # Statements (Cortex Values) wrap to multi-line text; give them width.
    if settings.get("has_statement"):
        return True
    return False


def build_rows(actor_type_def: dict, character: dict) -> list[list[dict]]:
    """Return a list of rows; each row is a list of 1 or 2 section descriptors.

    A descriptor is a dict with: {kind, label, icon, data, settings, full_width}
      kind        -- "prime_set" | "stress" | "milestones" | "notes"
      label       -- visible heading
      icon        -- FA icon name (or None)
      data        -- the underlying data
      settings    -- capability flags (for prime_set kinds)
      full_width  -- bool
    """
    sections: list[dict] = []
    char_extras = character.get("extras") or {}
    char_prime_sets = character.get("prime_sets") or {}

    # 1. Prime sets in actor-type definition order.
    for ps in actor_type_def.get("prime_sets", []):
        entries = char_prime_sets.get(ps["id"]) or []
        if not entries:
            continue
        sections.append({
            "kind": "prime_set",
            "ps_id": ps["id"],
            "label": ps.get("label", ps["id"]),
            "icon": ps.get("icon"),
            "settings": ps.get("settings", {}),
            "data": entries,
            "full_width": _is_wide_prime_set(ps, entries),
        })

    # 2. Extras in canonical order.
    extras_def = actor_type_def.get("extras") or {}

    if extras_def.get("stress", {}).get("enabled"):
        sections.append({
            "kind": "stress",
            "label": "Stress & Trauma",
            "icon": extras_def["stress"].get("icon", "shield-alt"),
            "settings": {},
            "data": {
                "tracks": extras_def["stress"].get("tracks", []),
                "trauma_enabled": extras_def["stress"].get("trauma_enabled", False),
                "stress": char_extras.get("stress") or {},
                "trauma": char_extras.get("trauma") or {},
            },
            "full_width": False,
        })

    if extras_def.get("milestones", {}).get("enabled") and char_extras.get("milestones"):
        sections.append({
            "kind": "milestones",
            "label": "Milestones",
            "icon": extras_def["milestones"].get("icon", "medal"),
            "settings": {},
            "data": char_extras["milestones"],
            "full_width": True,
        })

    if character.get("notes"):
        sections.append({
            "kind": "notes",
            "label": "Notes",
            "icon": "book-open",
            "settings": {},
            "data": character["notes"],
            "full_width": True,
        })

    # 3. Group into rows. Pair consecutive half-width sections; full-width
    #    sections close any pending half-width pair and stand alone.
    rows: list[list[dict]] = []
    pending: list[dict] = []
    for sec in sections:
        if sec["full_width"]:
            if pending:
                rows.append(pending)
                pending = []
            rows.append([sec])
        else:
            pending.append(sec)
            if len(pending) == 2:
                rows.append(pending)
                pending = []
    if pending:
        rows.append(pending)

    return rows


# ---------------------------------------------------------------------------
# Render entry point
# ---------------------------------------------------------------------------

def render_pdf(game_path: Path, character_path: Path, output_path: Path) -> Path:
    game_def: dict[str, Any] = json.loads(Path(game_path).read_text(encoding="utf-8"))
    character: dict[str, Any] = json.loads(Path(character_path).read_text(encoding="utf-8"))

    actor_type_def = resolve_actor_type(game_def, character.get("actor_type"))

    templates_dir = assets_dir() / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["dice"] = dice_icons
    env.globals["icon_glyph"] = icon_glyph

    template = env.get_template("sheet.html.j2")
    html_str = template.render(
        game=game_def,
        actor_type=actor_type_def,
        character=character,
        rows=build_rows(actor_type_def, character),
    )

    HTML(string=html_str, base_url=str(templates_dir)).write_pdf(str(output_path))
    return output_path

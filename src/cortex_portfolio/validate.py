"""Validate Cortex Prime game definitions and character files.

Two layers of validation:
  1. Game definition self-consistency (well-formedness, internal references).
  2. Character file conforms to a game definition (cross-validation).

Issues are accumulated rather than raised, so a single pass surfaces
everything wrong with a file. Severity is split:

  ERROR    -- would prevent valid rendering or violates a hard constraint.
              Examples: missing required top-level fields, unknown
              actor_type referenced by character, type mismatches that would
              crash iteration.

  WARNING  -- notable but the renderer can handle it. Examples: a die not in
              the allowed pool (renders as a red placeholder), counts
              outside min/max (still renders), unknown settings flag (typo).

Errors block rendering; warnings do not unless --strict is set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import VALID_DICE


# ---------------------------------------------------------------------------
# Settings flags we recognize. Anything outside this set is a "typo warning"
# so users get an early signal rather than silent ignoring at render time.
# ---------------------------------------------------------------------------

KNOWN_SETTINGS_FLAGS: frozenset[str] = frozenset({
    "has_label", "has_dice", "has_description", "has_statement",
    "has_sfx", "has_limits", "has_sub_traits",
    "sub_traits_label", "sub_traits_have_dice", "sub_traits_dice",
    "sub_traits_max", "limits_required",
})


# ---------------------------------------------------------------------------
# Issue records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    path: str      # e.g. "actor_types.character.prime_sets[2].dice[0]"
    message: str
    code: str = ""

    def is_error(self) -> bool:
        return self.severity == "error"

    def __str__(self) -> str:
        tag = "ERROR" if self.is_error() else "warn "
        return f"[{tag}] {self.path}: {self.message}"


@dataclass
class _Ctx:
    """Walk-context for accumulating issues."""
    issues: list[Issue] = field(default_factory=list)

    def err(self, path: str, msg: str, code: str = "") -> None:
        self.issues.append(Issue("error", path, msg, code))

    def warn(self, path: str, msg: str, code: str = "") -> None:
        self.issues.append(Issue("warning", path, msg, code))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(game_def: dict, character: dict | None = None) -> list[Issue]:
    """Validate a game definition and optionally a character.

    Returns a list of Issues in deterministic order. Use Issue.is_error()
    to filter for blocking problems.
    """
    ctx = _Ctx()
    _check_game_def(ctx, game_def, "game")
    if character is not None:
        _check_character(ctx, game_def, character, "character")
    return ctx.issues


def split(issues: Iterable[Issue]) -> tuple[list[Issue], list[Issue]]:
    """Convenience: split issues into (errors, warnings)."""
    errs: list[Issue] = []
    warns: list[Issue] = []
    for i in issues:
        (errs if i.is_error() else warns).append(i)
    return errs, warns


# ===========================================================================
# Game definition validation
# ===========================================================================

def _check_game_def(ctx: _Ctx, gd: Any, p: str) -> None:
    if not isinstance(gd, dict):
        ctx.err(p, "must be a JSON object")
        return

    for key in ("id", "name", "actor_types"):
        if key not in gd:
            ctx.err(f"{p}.{key}", "required field missing")

    pool = gd.get("dice_pool")
    if pool is None:
        ctx.warn(f"{p}.dice_pool", "no dice_pool declared; per-prime-set dice will be unrestricted")
    elif not isinstance(pool, list) or not pool:
        ctx.err(f"{p}.dice_pool", "must be a non-empty list of die strings")
    else:
        for i, d in enumerate(pool):
            if d not in VALID_DICE:
                ctx.warn(f"{p}.dice_pool[{i}]",
                         f"{d!r} is not a recognized die "
                         f"(expected one of {sorted(VALID_DICE)})")

    actor_types = gd.get("actor_types")
    if actor_types is None:
        return  # already errored above
    if not isinstance(actor_types, dict) or not actor_types:
        ctx.err(f"{p}.actor_types", "must be a non-empty mapping of id -> actor type")
        return

    for at_id, at_def in actor_types.items():
        _check_actor_type(ctx, at_def, gd, f"{p}.actor_types.{at_id}")


def _check_actor_type(ctx: _Ctx, at_def: Any, gd: dict, p: str) -> None:
    if not isinstance(at_def, dict):
        ctx.err(p, "must be a mapping")
        return

    if "label" not in at_def:
        ctx.warn(f"{p}.label", "no label set; renderer will fall back to id")

    prime_sets = at_def.get("prime_sets", [])
    if not isinstance(prime_sets, list):
        ctx.err(f"{p}.prime_sets", "must be a list")
        return

    seen_ids: set[str] = set()
    for i, ps in enumerate(prime_sets):
        ps_path = f"{p}.prime_sets[{i}]"
        if not isinstance(ps, dict):
            ctx.err(ps_path, "must be a mapping")
            continue
        ps_id = ps.get("id")
        if not ps_id:
            ctx.err(f"{ps_path}.id", "required")
        elif ps_id in seen_ids:
            ctx.err(f"{ps_path}.id", f"duplicate prime set id {ps_id!r} within actor type")
        else:
            seen_ids.add(ps_id)
        _check_prime_set(ctx, ps, gd, ps_path)

    extras = at_def.get("extras")
    if isinstance(extras, dict):
        _check_extras(ctx, extras, f"{p}.extras")


def _check_prime_set(ctx: _Ctx, ps: dict, gd: dict, p: str) -> None:
    if "label" not in ps:
        ctx.warn(f"{p}.label", "no label; renderer will fall back to id")

    settings = ps.get("settings", {})
    if not isinstance(settings, dict):
        ctx.err(f"{p}.settings", "must be a mapping")
        settings = {}
    else:
        for k in settings:
            if k not in KNOWN_SETTINGS_FLAGS:
                ctx.warn(f"{p}.settings.{k}", f"unknown settings flag {k!r}")

    if settings.get("has_sub_traits") and not settings.get("sub_traits_label"):
        ctx.warn(
            f"{p}.settings.sub_traits_label",
            "has_sub_traits is true but no sub_traits_label set; rendered heading will fall back to 'Sub-traits'",
        )

    pool = set(gd.get("dice_pool") or [])
    # Validate die-list fields wherever they appear (on prime_set or settings)
    for container, container_path in ((ps, p), (settings, f"{p}.settings")):
        for field_name in ("dice", "default_dice", "sub_traits_dice"):
            if field_name not in container:
                continue
            values = container[field_name]
            if not isinstance(values, list):
                ctx.err(f"{container_path}.{field_name}", "must be a list of die strings")
                continue
            for j, d in enumerate(values):
                if d not in VALID_DICE:
                    ctx.warn(f"{container_path}.{field_name}[{j}]",
                             f"{d!r} is not a recognized die")
                elif pool and d not in pool:
                    ctx.warn(f"{container_path}.{field_name}[{j}]",
                             f"{d!r} is not in the game's dice_pool {sorted(pool)}")

    count = ps.get("count")
    if isinstance(count, dict):
        cmin = count.get("min")
        cmax = count.get("max")
        for k, v in (("min", cmin), ("max", cmax)):
            if v is not None and (not isinstance(v, int) or v < 0):
                ctx.err(f"{p}.count.{k}", f"must be a non-negative integer; got {v!r}")
        if isinstance(cmin, int) and isinstance(cmax, int) and cmin > cmax:
            ctx.err(f"{p}.count", f"min ({cmin}) > max ({cmax})")

    items = ps.get("items")
    if items is not None:
        if not isinstance(items, list):
            ctx.err(f"{p}.items", "must be a list")
        else:
            seen: set[str] = set()
            for j, it in enumerate(items):
                if not isinstance(it, dict) or "name" not in it:
                    ctx.err(f"{p}.items[{j}]", "must be a mapping with a 'name' field")
                    continue
                n = it["name"]
                if n in seen:
                    ctx.warn(f"{p}.items[{j}].name", f"duplicate item name {n!r}")
                seen.add(n)


def _check_extras(ctx: _Ctx, extras: dict, p: str) -> None:
    s = extras.get("stress")
    if isinstance(s, dict) and s.get("enabled"):
        tracks = s.get("tracks", [])
        if not isinstance(tracks, list):
            ctx.err(f"{p}.stress.tracks", "must be a list")
        else:
            seen: set[str] = set()
            for j, t in enumerate(tracks):
                tp = f"{p}.stress.tracks[{j}]"
                if not isinstance(t, dict):
                    ctx.err(tp, "must be a mapping")
                    continue
                tid = t.get("id")
                if not tid:
                    ctx.err(f"{tp}.id", "required")
                elif tid in seen:
                    ctx.err(f"{tp}.id", f"duplicate stress track id {tid!r}")
                else:
                    seen.add(tid)
                if "label" not in t:
                    ctx.warn(f"{tp}.label", "no label set; will display as id")


# ===========================================================================
# Character validation
# ===========================================================================

def _check_character(ctx: _Ctx, gd: dict, ch: Any, p: str) -> None:
    if not isinstance(ch, dict):
        ctx.err(p, "must be a JSON object")
        return

    declared_game = ch.get("game_definition")
    if declared_game and declared_game != gd.get("id"):
        ctx.warn(
            f"{p}.game_definition",
            f"references {declared_game!r} but game definition id is {gd.get('id')!r}",
        )

    actor_type_id = ch.get("actor_type", "character")
    actor_types = gd.get("actor_types") or {}
    if actor_type_id not in actor_types:
        available = sorted(actor_types.keys()) if isinstance(actor_types, dict) else []
        ctx.err(
            f"{p}.actor_type",
            f"unknown actor type {actor_type_id!r}; "
            f"available: {available or '(none defined)'}",
        )
        return

    at_def = actor_types[actor_type_id]
    ps_defs: dict[str, dict] = {}
    for ps in at_def.get("prime_sets", []):
        if isinstance(ps, dict) and "id" in ps:
            ps_defs[ps["id"]] = ps

    char_prime_sets = ch.get("prime_sets")
    if char_prime_sets is None:
        ctx.warn(f"{p}.prime_sets", "no prime_sets data; sheet will only show extras")
        char_prime_sets = {}
    elif not isinstance(char_prime_sets, dict):
        ctx.err(f"{p}.prime_sets", "must be a mapping of prime_set_id -> entries list")
        return

    for ps_id, entries in char_prime_sets.items():
        ps_path = f"{p}.prime_sets.{ps_id}"
        if ps_id not in ps_defs:
            ctx.warn(
                ps_path,
                f"prime set {ps_id!r} not defined in actor type {actor_type_id!r}; "
                "will be ignored at render time",
            )
            continue
        if not isinstance(entries, list):
            ctx.err(ps_path, "must be a list of trait entries")
            continue
        _check_prime_set_entries(ctx, ps_defs[ps_id], gd, entries, ps_path)

    # Stress / trauma keys must point at defined tracks.
    extras_def = at_def.get("extras") or {}
    stress_def = extras_def.get("stress") or {}
    if stress_def.get("enabled"):
        track_ids = {
            t["id"]
            for t in stress_def.get("tracks", []) or []
            if isinstance(t, dict) and "id" in t
        }
        char_extras = ch.get("extras") or {}
        for field_name in ("stress", "trauma"):
            char_field = char_extras.get(field_name)
            if not isinstance(char_field, dict):
                continue
            for k, v in char_field.items():
                if k not in track_ids:
                    ctx.warn(
                        f"{p}.extras.{field_name}.{k}",
                        f"refers to undefined stress track {k!r}; "
                        f"defined tracks: {sorted(track_ids)}",
                    )
                elif v is not None and v not in VALID_DICE:
                    ctx.warn(
                        f"{p}.extras.{field_name}.{k}",
                        f"{v!r} is not a recognized die",
                    )


def _check_prime_set_entries(
    ctx: _Ctx, ps_def: dict, gd: dict, entries: list, p: str
) -> None:
    settings = ps_def.get("settings") or {}

    count = ps_def.get("count")
    if isinstance(count, dict):
        cmin, cmax = count.get("min"), count.get("max")
        if isinstance(cmin, int) and len(entries) < cmin:
            ctx.warn(p, f"has {len(entries)} entries; minimum is {cmin}")
        if isinstance(cmax, int) and len(entries) > cmax:
            ctx.warn(p, f"has {len(entries)} entries; maximum is {cmax}")

    items = ps_def.get("items")
    # NOTE: we no longer warn on names that aren't in `items`. The editor
    # treats predefined items as suggestions (a dropdown of common picks)
    # rather than constraints; players can type any name they want. The
    # `items` list still drives the editor's dropdown population, but
    # whether a typed name is "valid" is the game's call, not ours.

    seen_names: set[str] = set()
    allowed_dice = set(ps_def.get("dice") or settings.get("dice") or gd.get("dice_pool") or [])
    sub_allowed_dice = set(settings.get("sub_traits_dice") or []) or allowed_dice

    has_label = settings.get("has_label", True)
    has_dice = settings.get("has_dice", True)
    has_sub_traits = settings.get("has_sub_traits", False)
    has_sfx = settings.get("has_sfx", False)
    has_limits = settings.get("has_limits", False)
    sub_have_dice = settings.get("sub_traits_have_dice", True)

    for i, e in enumerate(entries):
        ep = f"{p}[{i}]"
        if not isinstance(e, dict):
            ctx.err(ep, "must be a mapping")
            continue

        name = e.get("name")
        if has_label and not name:
            ctx.warn(f"{ep}.name", "missing name")
        elif name is not None:
            if name in seen_names:
                ctx.warn(f"{ep}.name", f"duplicate trait name {name!r}")
            seen_names.add(name)

        # Dice
        _check_dice_field(
            ctx, e, "dice", f"{ep}.dice", allowed_dice, expected=has_dice
        )

        # Sub-traits
        sub_traits = e.get("sub_traits")
        if sub_traits:
            if not has_sub_traits:
                ctx.warn(
                    f"{ep}.sub_traits",
                    "trait has sub_traits but settings.has_sub_traits is false; "
                    "they will be ignored at render time",
                )
            else:
                if not isinstance(sub_traits, list):
                    ctx.err(f"{ep}.sub_traits", "must be a list")
                else:
                    sub_max = settings.get("sub_traits_max")
                    if isinstance(sub_max, int) and len(sub_traits) > sub_max:
                        ctx.warn(
                            f"{ep}.sub_traits",
                            f"has {len(sub_traits)} sub-traits; max is {sub_max}",
                        )
                    for j, st in enumerate(sub_traits):
                        stp = f"{ep}.sub_traits[{j}]"
                        if not isinstance(st, dict):
                            ctx.err(stp, "must be a mapping")
                            continue
                        if not st.get("name"):
                            ctx.warn(f"{stp}.name", "missing name")
                        _check_dice_field(
                            ctx, st, "dice", f"{stp}.dice",
                            sub_allowed_dice, expected=sub_have_dice,
                        )

        # SFX
        if e.get("sfx"):
            if not has_sfx:
                ctx.warn(
                    f"{ep}.sfx",
                    "trait has sfx but settings.has_sfx is false; "
                    "they will be ignored at render time",
                )
            elif not isinstance(e["sfx"], list):
                ctx.err(f"{ep}.sfx", "must be a list")

        # Limits
        if e.get("limits"):
            if not has_limits:
                ctx.warn(
                    f"{ep}.limits",
                    "trait has limits but settings.has_limits is false; "
                    "they will be ignored at render time",
                )
            elif not isinstance(e["limits"], list):
                ctx.err(f"{ep}.limits", "must be a list")

        lr = settings.get("limits_required")
        if isinstance(lr, dict) and isinstance(lr.get("min"), int):
            n_lim = len(e.get("limits") or [])
            if n_lim < lr["min"]:
                ctx.warn(
                    f"{ep}.limits",
                    f"has {n_lim} limits; minimum required is {lr['min']}",
                )


def _check_dice_field(
    ctx: _Ctx,
    obj: dict,
    field_name: str,
    path: str,
    allowed: set[str],
    *,
    expected: bool,
) -> None:
    """Validate that `obj[field_name]` is a list of valid die strings."""
    if field_name not in obj or obj[field_name] is None:
        return
    raw = obj[field_name]
    if not expected and raw:
        ctx.warn(path, "settings does not declare dice on this trait but data is present; will be ignored")
        return
    # Tolerate a single string for forward compat with the v1 schema
    if isinstance(raw, str):
        ctx.warn(path, "should be a list (e.g. [\"d8\"]); single string is a v1 leftover")
        raw = [raw]
    if not isinstance(raw, list):
        ctx.err(path, "must be a list of die strings")
        return
    for j, d in enumerate(raw):
        if d not in VALID_DICE:
            ctx.warn(f"{path}[{j}]", f"{d!r} is not a recognized die")
        elif allowed and d not in allowed:
            ctx.warn(
                f"{path}[{j}]",
                f"{d!r} is not in this trait's allowed dice {sorted(allowed)}",
            )

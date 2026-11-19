# PinhOS Phase 2 — Unified Theme Engine (core/theme.py)
# Loads and validates JSON themes from /sd/pinhos/themes/, builds 16-entry RGB565 LUTs
# for zero-framebuffer 4-bit indexed rendering, and supports runtime hot-swapping.
# Zero hardcoded GPIO pins outside boards/.

import os
import gc
import json
import array

from boards.base import rgb565, rgb565_swap

DEFAULT_THEMES_DIR = "/sd/pinhos/themes"

CANONICAL_THEME_IDS = (
    "cyber_amber",
    "phosphor_green",
    "arctic_daylight",
    "synthwave_pulse",
)

# Map legacy Phase 1 theme aliases to canonical Phase 2 theme IDs
THEME_ALIASES = {
    "amber_phosphor": "cyber_amber",
    "matrix_green": "phosphor_green",
    "high_contrast": "arctic_daylight",
    "cyber_cyan": "synthwave_pulse",
}

REQUIRED_TOKENS = (
    "bg",
    "surface",
    "border",
    "text",
    "text_muted",
    "accent",
    "accent_fg",
    "ok",
    "warn",
    "err",
)

# Canonical 4-bit palette index map (0..15) shared by GUI, TUI, and sandboxed apps.
# Preserves backward compatibility with Phase 1 indices:
#   0=bg, 3=accent, 6=text_muted, 9=err, 10=ok, 11=warn, 15=text
PALETTE_INDEX = {
    "bg": 0,
    "surface": 1,
    "border": 2,
    "accent": 3,
    "accent_fg": 4,
    "sel_bg": 5,
    "text_muted": 6,
    "fg_muted": 6,
    "sel_fg": 7,
    "surface_alt": 8,
    "err": 9,
    "ok": 10,
    "warn": 11,
    "accent_alt": 12,
    "highlight": 13,
    "info": 14,
    "text": 15,
    "fg": 15,
}

BUILTIN_FALLBACK_THEME = {
    "id": "cyber_amber",
    "name": "Cyber Amber",
    "author": "bpinh0",
    "version": "1.0.0",
    "layout": "LIST",
    "font_scale": 1.0,
    "colors": {
        "bg": "#0A0C10",
        "surface": "#12161F",
        "fg": "#FFB000",
        "fg_muted": "#9E7216",
        "accent": "#00E5FF",
        "accent_fg": "#0A0C10",
        "border": "#FFB000",
        "sel_bg": "#FFB000",
        "sel_fg": "#0A0C10",
        "ok": "#00FF9C",
        "warn": "#FF9900",
        "err": "#FF3355",
    },
}


class ThemeError(Exception):
    """Raised when a theme JSON file is missing or violates the theme schema."""
    pass


def parse_hex_color(hex_str):
    """Parse '#RRGGBB' hex string into (r, g, b) tuple of ints 0..255."""
    if not isinstance(hex_str, str):
        raise ThemeError("Color value must be a string: {!r}".format(hex_str))
    s = hex_str.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        raise ThemeError("Invalid hex color length: {!r}".format(hex_str))
    try:
        val = int(s, 16)
    except ValueError:
        raise ThemeError("Invalid hex digits in color: {!r}".format(hex_str))
    return ((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)


def _blend_rgb(c1, c2, num, den):
    """Blend two (r, g, b) tuples using integer arithmetic."""
    inv = den - num
    return (
        (c1[0] * inv + c2[0] * num) // den,
        (c1[1] * inv + c2[1] * num) // den,
        (c1[2] * inv + c2[2] * num) // den,
    )


def _normalize_colors(raw_colors):
    """
    Resolve semantic color tokens from a raw JSON 'colors' dict, supporting both
    (fg / fg_muted) and (text / text_muted) aliases with fallback defaults.
    """
    if not isinstance(raw_colors, dict):
        raise ThemeError("Theme 'colors' must be a dictionary")

    fb = BUILTIN_FALLBACK_THEME["colors"]
    resolved = {}

    # Primary text & muted text support both 'text'/'fg' and 'text_muted'/'fg_muted'
    text_hex = raw_colors.get("text") or raw_colors.get("fg")
    muted_hex = raw_colors.get("text_muted") or raw_colors.get("fg_muted")

    if not text_hex:
        raise ThemeError("Theme colors missing 'text' / 'fg'")
    if not muted_hex:
        raise ThemeError("Theme colors missing 'text_muted' / 'fg_muted'")

    resolved["text"] = text_hex
    resolved["fg"] = text_hex
    resolved["text_muted"] = muted_hex
    resolved["fg_muted"] = muted_hex

    for key in ("bg", "surface", "border", "accent", "accent_fg", "ok", "warn", "err"):
        val = raw_colors.get(key)
        if not val:
            raise ThemeError("Theme colors missing required token '{}'".format(key))
        resolved[key] = val

    resolved["sel_bg"] = raw_colors.get("sel_bg") or resolved["accent"]
    resolved["sel_fg"] = raw_colors.get("sel_fg") or resolved["accent_fg"]
    resolved["accent_alt"] = raw_colors.get("accent_alt") or resolved["accent"]
    resolved["info"] = raw_colors.get("info") or resolved["accent"]

    # Validate every hex string
    for k, hx in resolved.items():
        parse_hex_color(hx)

    # Ensure fallback keys exist even if not explicitly provided
    for k, hx in fb.items():
        if k not in resolved:
            resolved[k] = hx

    return resolved


def validate_theme_dict(data):
    """
    Validate a parsed theme JSON dictionary.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if not isinstance(data, dict):
        return (False, "Theme root must be a JSON object")
    tid = data.get("id")
    if not isinstance(tid, str) or not tid.strip():
        return (False, "Theme missing non-empty string 'id'")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return (False, "Theme missing non-empty string 'name'")
    try:
        _normalize_colors(data.get("colors"))
    except ThemeError as exc:
        return (False, str(exc))
    return (True, None)


class Theme:
    """Resolved PinhOS theme with semantic token lookup and 16-entry RGB565 LUT."""

    def __init__(self, data):
        ok, err = validate_theme_dict(data)
        if not ok:
            raise ThemeError(err)

        self.id = data["id"].strip()
        self.name = data["name"].strip()
        self.author = str(data.get("author", "PinhOS"))
        self.version = str(data.get("version", "1.0.0"))
        self.layout = str(data.get("layout", "LIST")).upper()
        self.colors = _normalize_colors(data["colors"])

        # Precompute RGB tuples, standard RGB565 values, and 16-entry byte-swapped LUT
        self._rgb = {}
        self._rgb565 = {}
        for tok, hx in self.colors.items():
            r, g, b = parse_hex_color(hx)
            self._rgb[tok] = (r, g, b)
            self._rgb565[tok] = rgb565(r, g, b)

        # Compute subtle surface_alt for secondary headers/footers
        surf_alt = _blend_rgb(self._rgb["surface"], self._rgb["border"], 1, 5)
        self._rgb["surface_alt"] = surf_alt
        self._rgb565["surface_alt"] = rgb565(surf_alt[0], surf_alt[1], surf_alt[2])
        self._rgb["highlight"] = self._rgb["sel_bg"]
        self._rgb565["highlight"] = self._rgb565["sel_bg"]

        self.lut = self._build_lut()

    def _build_lut(self):
        slot_tokens = (
            "bg",           # 0
            "surface",      # 1
            "border",       # 2
            "accent",       # 3
            "accent_fg",    # 4
            "sel_bg",       # 5
            "text_muted",   # 6
            "sel_fg",       # 7
            "surface_alt",  # 8
            "err",          # 9
            "ok",           # 10
            "warn",         # 11
            "accent_alt",   # 12
            "highlight",    # 13
            "info",         # 14
            "text",         # 15
        )
        entries = []
        for tok in slot_tokens:
            r, g, b = self._rgb[tok]
            entries.append(rgb565_swap(r, g, b))
        if entries[0] == entries[15] or entries[0] == entries[3]:
            raise ThemeError("Theme foreground/accent matches background (invisible palette)")
        return array.array("H", entries)

    def color(self, token, default="text"):
        """Return 4-bit palette index (0..15) for a semantic token."""
        idx = PALETTE_INDEX.get(token)
        if idx is not None:
            return idx
        return PALETTE_INDEX.get(default, 15)

    def hex(self, token, default="text"):
        """Return '#RRGGBB' hex string for a semantic token."""
        if token in self.colors:
            return self.colors[token]
        return self.colors.get(default, "#FFFFFF")

    def rgb565(self, token, default="text"):
        """Return 16-bit standard RGB565 integer for a semantic token."""
        if token in self._rgb565:
            return self._rgb565[token]
        return self._rgb565.get(default, 0xFFFF)

    def __repr__(self):
        return "<Theme id={!r} name={!r}>".format(self.id, self.name)


def load_theme_file(path, strict=False):
    """
    Load and validate a JSON theme file from disk.
    When strict=False, falls back cleanly to BUILTIN_FALLBACK_THEME on error.
    """
    try:
        with open(path, "r") as f:
            raw = f.read()
        # Strip UTF-8 BOM defensively if present
        if raw.startswith("\ufeff"):
            raw = raw[1:]
        data = json.loads(raw)
        return Theme(data)
    except Exception as exc:
        if strict:
            if isinstance(exc, ThemeError):
                raise
            raise ThemeError("Failed to load theme '{}': {}".format(path, exc))
        return Theme(BUILTIN_FALLBACK_THEME)


class ThemeManager:
    """
    Manages PinhOS themes: discovery, validation, LUT activation on board HAL,
    config.json persistence, and hot-swap listener notifications.
    """

    def __init__(self, themes_dir=DEFAULT_THEMES_DIR, config=None, board=None):
        self.themes_dir = themes_dir.rstrip("/") if themes_dir else DEFAULT_THEMES_DIR
        self.config = config
        self.board = board
        self._listeners = []
        self._theme_ids = []
        self.active = Theme(BUILTIN_FALLBACK_THEME)

        self.refresh_catalog()
        initial_id = "cyber_amber"
        if self.config is not None:
            initial_id = self.config.get("theme", "cyber_amber")
        self.apply(initial_id, persist=False, notify=False)

    def _normalize_id(self, theme_id):
        if not theme_id:
            return "cyber_amber"
        tid = str(theme_id).strip().lower()
        if tid.endswith(".json"):
            tid = tid[:-5]
        return THEME_ALIASES.get(tid, tid)

    def _theme_path(self, theme_id):
        return self.themes_dir + "/" + self._normalize_id(theme_id) + ".json"

    def refresh_catalog(self):
        """Scan themes_dir for valid .json theme files, keeping canonical order first."""
        found = []
        try:
            entries = os.listdir(self.themes_dir)
            for fname in entries:
                if fname.endswith(".json") and not fname.startswith("."):
                    found.append(fname[:-5])
        except Exception:
            found = []

        ordered = []
        for cid in CANONICAL_THEME_IDS:
            if cid in found:
                ordered.append(cid)
        for fid in sorted(found):
            if fid not in ordered:
                ordered.append(fid)

        if not ordered:
            ordered = ["cyber_amber"]
        self._theme_ids = ordered
        return list(self._theme_ids)

    def list_themes(self):
        if not self._theme_ids:
            self.refresh_catalog()
        return list(self._theme_ids)

    def load(self, theme_id, strict=False):
        """Load a Theme by ID without activating it."""
        tid = self._normalize_id(theme_id)
        path = self._theme_path(tid)
        return load_theme_file(path, strict=strict)

    def apply(self, theme_id, persist=True, notify=True):
        """
        Load and activate a theme by ID, pushing its 16-entry RGB565 LUT to the
        board HAL, persisting to config.json, and notifying registered UI listeners.
        """
        tid = self._normalize_id(theme_id)
        theme = self.load(tid, strict=False)
        self.active = theme

        if self.board is not None and hasattr(self.board, "set_lut"):
            try:
                self.board.set_lut(theme.lut)
            except Exception:
                pass

        if persist and self.config is not None:
            try:
                self.config.set("theme", theme.id, save_now=True)
            except Exception:
                pass

        if notify:
            for cb in list(self._listeners):
                try:
                    cb(theme)
                except Exception:
                    pass

        gc.collect()
        return theme

    def cycle(self, step=1, persist=True):
        """Cycle to the next (or previous) available theme and activate it."""
        ids = self.list_themes()
        if not ids:
            return self.active
        try:
            idx = ids.index(self.active.id)
        except ValueError:
            idx = 0
        next_id = ids[(idx + int(step)) % len(ids)]
        return self.apply(next_id, persist=persist, notify=True)

    def register_listener(self, callback):
        if callable(callback) and callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback):
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def color(self, token, default="text"):
        return self.active.color(token, default=default)

    def hex(self, token, default="text"):
        return self.active.hex(token, default=default)

    def rgb565(self, token, default="text"):
        return self.active.rgb565(token, default=default)

    def validate_all(self):
        """Strictly load and validate all JSON theme files in themes_dir."""
        results = {}
        for tid in self.list_themes():
            path = self._theme_path(tid)
            try:
                t = load_theme_file(path, strict=True)
                results[tid] = (True, t.name)
            except Exception as exc:
                results[tid] = (False, str(exc))
        return results


_singleton_theme_manager = None


def get_theme_manager(themes_dir=DEFAULT_THEMES_DIR, config=None, board=None, force_new=False):
    global _singleton_theme_manager
    if _singleton_theme_manager is None or force_new:
        _singleton_theme_manager = ThemeManager(
            themes_dir=themes_dir,
            config=config,
            board=board,
        )
    else:
        if board is not None:
            _singleton_theme_manager.board = board
            try:
                board.set_lut(_singleton_theme_manager.active.lut)
            except Exception:
                pass
        if config is not None:
            _singleton_theme_manager.config = config
    return _singleton_theme_manager

# PinhOS Phase 2 + Phase 5 — Unified Theme Engine & Schema v2 (core/theme.py)
# Loads and validates Schema v1/v2 & flat legacy JSON themes from /sd/pinhos/themes/,
# deep-merges color/style/font/banner tokens onto defaults, pre-computes RGB565 ints
# + 16-entry RGB565 LUTs + cached 6x8 glyph memoryviews, and supports live hot-swapping.
# Zero hardcoded GPIO pins outside boards/.

import os
import gc
import json
import array

from boards.base import rgb565, rgb565_swap

DEFAULT_THEMES_DIR = "/sd/pinhos/themes"
DEFAULT_BANNERS_DIR = "/sd/pinhos/banners"

CANONICAL_THEME_IDS = (
    "cyber_amber",
    "obsidian_amber",
    "phosphor_green",
    "arctic_daylight",
    "synthwave_pulse",
)

# Map legacy Phase 1 theme aliases to canonical theme IDs
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

VALID_BORDER_STYLES = ("single", "double", "rounded", "none")
VALID_BAR_STYLES = ("blocks", "solid", "striped")
VALID_CARD_HEADERS = ("filled", "tinted", "underline")
VALID_QUICK_STRIPS = ("pills", "tabs")

DEFAULT_STYLE = {
    "border_style": "single",
    "bar_style": "solid",
    "card_header": "filled",
    "quick_strip": "pills",
}

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
    "header_bg": 12,
    "accent_alt": 12,
    "border_focus": 13,
    "highlight": 13,
    "info": 14,
    "text": 15,
    "fg": 15,
    "header_fg": 4,
    "footer_bg": 12,
    "footer_fg": 4,
}

BUILTIN_FALLBACK_THEME = {
    "id": "cyber_amber",
    "name": "Cyber Amber",
    "author": "bpinh0",
    "version": 2,
    "layout": "LIST",
    "font": "default",
    "uppercase_headers": False,
    "colors": {
        "bg": "#0A0C10",
        "surface": "#12161F",
        "fg": "#FFB000",
        "text": "#FFB000",
        "fg_muted": "#9E7216",
        "text_muted": "#9E7216",
        "accent": "#00E5FF",
        "accent_fg": "#0A0C10",
        "border": "#FFB000",
        "sel_bg": "#FFB000",
        "sel_fg": "#0A0C10",
        "ok": "#00FF9C",
        "warn": "#FF9900",
        "err": "#FF3355",
    },
    "style": dict(DEFAULT_STYLE),
    "banner": None,
}

_FLAT_COLOR_KEYS = (
    "bg", "surface", "surface_alt", "header_bg", "header_fg", "footer_bg", "footer_fg",
    "text", "fg", "text_muted", "fg_muted", "accent", "accent_fg", "sel_bg", "sel_fg",
    "border", "border_focus", "ok", "warn", "err", "info", "accent_alt",
)


class ThemeError(Exception):
    """Raised when a theme JSON file is missing or violates the theme schema."""
    pass


def _slug_id(s):
    out = []
    for ch in str(s or "").strip().lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
        elif ch in (" ", "-", "_") and (not out or out[-1] != "_"):
            out.append("_")
    return "".join(out).strip("_")


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


def _rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(rgb[0] & 0xFF, rgb[1] & 0xFF, rgb[2] & 0xFF)


def _blend_rgb(c1, c2, num, den):
    """Blend two (r, g, b) tuples using integer arithmetic."""
    inv = den - num
    return (
        (c1[0] * inv + c2[0] * num) // den,
        (c1[1] * inv + c2[1] * num) // den,
        (c1[2] * inv + c2[2] * num) // den,
    )


def _extract_raw_colors(data):
    """Extract raw color map from either data['colors'] or flat legacy root keys."""
    if not isinstance(data, dict):
        raise ThemeError("Theme root must be a JSON object")
    rc = data.get("colors")
    if isinstance(rc, dict):
        return rc
    if rc is not None:
        raise ThemeError("Theme 'colors' must be a dictionary")
    flat = {}
    for k in _FLAT_COLOR_KEYS:
        if k in data and data[k] is not None:
            flat[k] = data[k]
    if not flat:
        raise ThemeError("Theme missing 'colors' dictionary")
    return flat


def _normalize_colors(raw_colors, strict_required=False):
    """
    Deep-merge raw JSON color tokens onto built-in defaults, supporting Schema v2
    tokens (surface_alt, header_bg/fg, footer_bg/fg, border_focus), Schema v1
    (fg / fg_muted), and partial/flat legacy themes.
    """
    if not isinstance(raw_colors, dict):
        raise ThemeError("Theme 'colors' must be a dictionary")
    if not raw_colors:
        raise ThemeError("Theme 'colors' cannot be empty")

    # Validate every explicitly supplied color string first
    for k, hx in raw_colors.items():
        if hx is not None:
            parse_hex_color(hx)

    fb = BUILTIN_FALLBACK_THEME["colors"]
    resolved = {}

    text_hex = raw_colors.get("text") or raw_colors.get("fg")
    muted_hex = raw_colors.get("text_muted") or raw_colors.get("fg_muted")

    if strict_required:
        if not text_hex:
            raise ThemeError("Theme colors missing 'text' / 'fg'")
        if not muted_hex:
            raise ThemeError("Theme colors missing 'text_muted' / 'fg_muted'")
        for key in ("bg", "surface", "border", "accent", "accent_fg", "ok", "warn", "err"):
            if not raw_colors.get(key):
                raise ThemeError("Theme colors missing required token '{}'".format(key))

    text_hex = text_hex or fb["text"]
    muted_hex = muted_hex or fb["text_muted"]
    resolved["text"] = text_hex
    resolved["fg"] = text_hex
    resolved["text_muted"] = muted_hex
    resolved["fg_muted"] = muted_hex

    for key in ("bg", "surface", "border", "accent", "accent_fg", "ok", "warn", "err"):
        resolved[key] = raw_colors.get(key) or fb[key]

    resolved["sel_bg"] = raw_colors.get("sel_bg") or resolved["accent"]
    resolved["sel_fg"] = raw_colors.get("sel_fg") or resolved["accent_fg"]
    resolved["header_bg"] = raw_colors.get("header_bg") or resolved["accent"]
    resolved["header_fg"] = raw_colors.get("header_fg") or resolved["accent_fg"]
    resolved["footer_bg"] = raw_colors.get("footer_bg") or resolved["header_bg"]
    resolved["footer_fg"] = raw_colors.get("footer_fg") or resolved["header_fg"]
    resolved["border_focus"] = raw_colors.get("border_focus") or resolved["accent"]
    resolved["accent_alt"] = raw_colors.get("accent_alt") or resolved["header_bg"]
    resolved["info"] = raw_colors.get("info") or resolved["accent"]

    if raw_colors.get("surface_alt"):
        resolved["surface_alt"] = raw_colors["surface_alt"]
    else:
        s_rgb = parse_hex_color(resolved["surface"])
        b_rgb = parse_hex_color(resolved["border"])
        resolved["surface_alt"] = _rgb_to_hex(_blend_rgb(s_rgb, b_rgb, 1, 5))

    resolved["highlight"] = resolved["border_focus"]
    return resolved


def _normalize_style(raw_style):
    st = dict(DEFAULT_STYLE)
    if not isinstance(raw_style, dict):
        return st
    bs = str(raw_style.get("border_style", st["border_style"])).strip().lower()
    if bs in VALID_BORDER_STYLES:
        st["border_style"] = bs
    br = str(raw_style.get("bar_style", st["bar_style"])).strip().lower()
    if br in VALID_BAR_STYLES:
        st["bar_style"] = br
    ch = str(raw_style.get("card_header", st["card_header"])).strip().lower()
    if ch in VALID_CARD_HEADERS:
        st["card_header"] = ch
    qs = str(raw_style.get("quick_strip", st["quick_strip"])).strip().lower()
    if qs in VALID_QUICK_STRIPS:
        st["quick_strip"] = qs
    return st


def _load_banner_lines(banner_spec, banners_dir=DEFAULT_BANNERS_DIR, cols=23, max_rows=10):
    """Resolve optional theme banner (inline list of strings or <=1KB .txt file) clamped to pane."""
    if not banner_spec:
        return ()
    raw_lines = None
    if isinstance(banner_spec, (list, tuple)):
        raw_lines = [str(x) for x in banner_spec]
    elif isinstance(banner_spec, str):
        s = banner_spec.strip()
        if not s:
            return ()
        if "\n" in s:
            raw_lines = s.split("\n")
        else:
            p = s if s.startswith("/") else (banners_dir.rstrip("/") + "/" + (s if s.endswith(".txt") else s + ".txt"))
            try:
                with open(p, "rb") as f:
                    raw = f.read(1024).decode("utf-8", "ignore")
                raw_lines = raw.split("\n")
            except Exception:
                return ()
    if not raw_lines:
        return ()
    out = []
    for ln in raw_lines:
        clean = "".join([c if " " <= c <= "~" else " " for c in ln.replace("\r", "").replace("\t", "  ")]).rstrip()
        out.append(clean[:cols])
        if len(out) >= max_rows:
            break
    while out and not out[-1]:
        out.pop()
    return tuple(out)


def validate_theme_dict(data):
    """
    Validate a parsed theme JSON dictionary (Schema v1, Schema v2, or legacy flat).
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if not isinstance(data, dict):
        return (False, "Theme root must be a JSON object")
    tid = data.get("id")
    name = data.get("name")
    has_id = isinstance(tid, str) and bool(tid.strip())
    has_name = isinstance(name, str) and bool(name.strip())
    if not has_id and not has_name:
        return (False, "Theme missing non-empty string 'id' or 'name'")
    try:
        rc = _extract_raw_colors(data)
        cols = _normalize_colors(rc, strict_required=False)
        bg_sw = rgb565_swap(*parse_hex_color(cols["bg"]))
        tx_sw = rgb565_swap(*parse_hex_color(cols["text"]))
        ac_sw = rgb565_swap(*parse_hex_color(cols["accent"]))
        if bg_sw == tx_sw or bg_sw == ac_sw:
            return (False, "Theme foreground/accent matches background (invisible palette)")
    except ThemeError as exc:
        return (False, str(exc))
    return (True, None)


class Theme:
    """Resolved PinhOS theme (Schema v1/v2) with pre-computed RGB565 ints, LUT, style & 6x8 font."""

    def __init__(self, data, fallback_id=None, fonts_dir=None, banners_dir=DEFAULT_BANNERS_DIR):
        ok, err = validate_theme_dict(data)
        if not ok:
            raise ThemeError(err)

        raw_id = data.get("id")
        raw_name = data.get("name")
        if isinstance(raw_id, str) and raw_id.strip():
            self.id = raw_id.strip().lower()
        elif fallback_id:
            self.id = _slug_id(fallback_id) or "custom_theme"
        else:
            self.id = _slug_id(raw_name) or "custom_theme"

        if isinstance(raw_name, str) and raw_name.strip():
            self.name = raw_name.strip()
        else:
            self.name = " ".join([w[0].upper() + w[1:] for w in self.id.split("_") if w]) or self.id

        self.author = str(data.get("author", "PinhOS"))
        raw_ver = data.get("version", 2)
        self.schema_version = 2 if (raw_ver == 2 or str(raw_ver).startswith("2")) else 1
        self.version = str(raw_ver)
        self.layout = str(data.get("layout", "LIST")).upper()
        self.uppercase_headers = bool(data.get("uppercase_headers", False))
        self.style = _normalize_style(data.get("style"))
        self.banner = data.get("banner", None)
        self.banner_lines = _load_banner_lines(self.banner, banners_dir=banners_dir)

        req_font = str(data.get("font") or "default").strip().lower()
        try:
            from ui.fonts import get_font
            self.font_mv, self.font = get_font(req_font, fonts_dir=fonts_dir)
        except Exception:
            self.font_mv = None
            self.font = "default"

        rc = _extract_raw_colors(data)
        self.colors = _normalize_colors(rc, strict_required=False)

        # Precompute RGB tuples, standard RGB565 ints, and swapped RGB565 ints once on load
        self._rgb = {}
        self._rgb565 = {}
        self._swapped = {}
        for tok, hx in self.colors.items():
            r, g, b = parse_hex_color(hx)
            self._rgb[tok] = (r, g, b)
            self._rgb565[tok] = rgb565(r, g, b)
            self._swapped[tok] = rgb565_swap(r, g, b)

        self._slot_map = dict(PALETTE_INDEX)
        self.lut = self._build_lut()

    def _build_lut(self):
        slot_tokens = [
            "bg",            # 0
            "surface",       # 1
            "border",        # 2
            "accent",        # 3
            "accent_fg",     # 4
            "sel_bg",        # 5
            "text_muted",    # 6
            "sel_fg",        # 7
            "surface_alt",   # 8
            "err",           # 9
            "ok",            # 10
            "warn",          # 11
            "header_bg",     # 12
            "border_focus",  # 13
            "info",          # 14
            "text",          # 15
        ]
        entries = [self._swapped[tok] for tok in slot_tokens]
        if entries[0] == entries[15] or entries[0] == entries[3]:
            raise ThemeError("Theme foreground/accent matches background (invisible palette)")

        # Reclaim duplicate auxiliary slots 12/13 if footer_bg/header_fg/footer_fg use distinct colors
        free_aux = []
        if entries[12] == entries[3]:
            self._slot_map["header_bg"] = 3
            self._slot_map["accent_alt"] = 3
            free_aux.append(12)
        if entries[13] in (entries[3], entries[5]):
            self._slot_map["border_focus"] = 3 if entries[13] == entries[3] else 5
            self._slot_map["highlight"] = self._slot_map["border_focus"]
            free_aux.append(13)

        for extra_tok, fb_slot in (("footer_bg", 12), ("header_fg", 4), ("footer_fg", 4)):
            sw = self._swapped[extra_tok]
            matched = -1
            for idx in range(16):
                if entries[idx] == sw:
                    matched = idx
                    break
            if matched >= 0:
                self._slot_map[extra_tok] = matched
            elif free_aux:
                slot = free_aux.pop(0)
                entries[slot] = sw
                self._slot_map[extra_tok] = slot
            else:
                self._slot_map[extra_tok] = self._slot_map.get("header_bg", 3) if fb_slot == 12 else 4

        return array.array("H", entries)

    def color(self, token, default="text"):
        """Return 4-bit palette index (0..15) for a semantic token."""
        idx = self._slot_map.get(token)
        if idx is not None:
            return idx
        return self._slot_map.get(default, 15)

    def hex(self, token, default="text"):
        """Return '#RRGGBB' hex string for a semantic token."""
        if token in self.colors:
            return self.colors[token]
        return self.colors.get(default, "#FFFFFF")

    def rgb565(self, token, default="text"):
        """Return pre-computed 16-bit standard RGB565 integer for a semantic token."""
        if token in self._rgb565:
            return self._rgb565[token]
        return self._rgb565.get(default, 0xFFFF)

    def style_token(self, key, default=None):
        """Return resolved widget chrome style token ('border_style', 'bar_style', 'card_header', 'quick_strip')."""
        if key in self.style:
            return self.style[key]
        if default is not None:
            return default
        return DEFAULT_STYLE.get(key, "")

    def format_header(self, text):
        """Format card/bar header text respecting 'uppercase_headers'."""
        s = str(text)
        return s.upper() if self.uppercase_headers else s

    def __repr__(self):
        return "<Theme id={!r} name={!r} v{} font={!r}>".format(
            self.id, self.name, self.schema_version, self.font
        )


def load_theme_file(path, strict=False, fonts_dir=None, banners_dir=DEFAULT_BANNERS_DIR):
    """
    Load and validate a JSON theme file from disk.
    When strict=False, falls back cleanly to BUILTIN_FALLBACK_THEME on error.
    """
    stem = str(path or "").replace("\\", "/").rpartition("/")[2]
    if stem.lower().endswith(".json"):
        stem = stem[:-5]
    try:
        with open(path, "r") as f:
            raw = f.read()
        if raw.startswith("\ufeff"):
            raw = raw[1:]
        data = json.loads(raw)
        return Theme(data, fallback_id=stem, fonts_dir=fonts_dir, banners_dir=banners_dir)
    except Exception as exc:
        if strict:
            if isinstance(exc, ThemeError):
                raise
            raise ThemeError("Failed to load theme '{}': {}".format(path, exc))
        return Theme(BUILTIN_FALLBACK_THEME)


class ThemeManager:
    """
    Manages PinhOS themes: discovery, validation, LUT + 6x8 font activation on board HAL,
    config.json persistence, and hot-swap listener notifications.
    """

    def __init__(self, themes_dir=DEFAULT_THEMES_DIR, config=None, board=None):
        self.themes_dir = themes_dir.rstrip("/") if themes_dir else DEFAULT_THEMES_DIR
        root_dir = self.themes_dir.rpartition("/")[0] or "/sd/pinhos"
        self.fonts_dir = root_dir + "/fonts"
        self.banners_dir = root_dir + "/banners"
        self.config = config
        self.board = board
        self._listeners = []
        self._theme_ids = []
        self.active = Theme(BUILTIN_FALLBACK_THEME, fonts_dir=self.fonts_dir, banners_dir=self.banners_dir)

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
        return load_theme_file(
            path,
            strict=strict,
            fonts_dir=self.fonts_dir,
            banners_dir=self.banners_dir,
        )

    def _push_to_board(self, theme):
        if self.board is None:
            return
        if hasattr(self.board, "set_lut"):
            try:
                self.board.set_lut(theme.lut)
            except Exception:
                pass
        if hasattr(self.board, "set_font"):
            try:
                self.board.set_font(theme.font, theme.font_mv)
            except Exception:
                pass

    def apply(self, theme_id, persist=True, notify=True):
        """
        Load and activate a theme by ID, pushing its 16-entry RGB565 LUT and 6x8
        bitmap font to the board HAL, persisting to config.json, and notifying listeners.
        """
        tid = self._normalize_id(theme_id)
        theme = self.load(tid, strict=False)
        self.active = theme
        self._push_to_board(theme)

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

    def style_token(self, key, default=None):
        return self.active.style_token(key, default=default)

    def validate_all(self):
        """Strictly load and validate all JSON theme files in themes_dir."""
        results = {}
        for tid in self.list_themes():
            path = self._theme_path(tid)
            try:
                t = load_theme_file(
                    path,
                    strict=True,
                    fonts_dir=self.fonts_dir,
                    banners_dir=self.banners_dir,
                )
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
            _singleton_theme_manager._push_to_board(_singleton_theme_manager.active)
        if config is not None:
            _singleton_theme_manager.config = config
    return _singleton_theme_manager

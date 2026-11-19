# PinhOS Phase 2 — Dual-UI Engine & Focus/Mode Controller (ui/engine.py)
# Coordinates GUI/TUI rendering backends, unified ThemeManager hot-swapping,
# dirty-region partial redraws, and config.json persistence.
# Zero full-screen framebuffers; zero hardcoded GPIO pins.

import gc

from ui.gui import GUIBackend
from ui.tui import TUIBackend

VALID_UI_MODES = ("gui", "tui")

_MODE_ALIASES = {
    "native": "gui",
    "graphical": "gui",
    "lvgl": "gui",
    "terminal": "tui",
    "text": "tui",
    "cli": "tui",
}


def normalize_ui_mode(mode):
    if not mode:
        return "gui"
    m = str(mode).strip().lower()
    m = _MODE_ALIASES.get(m, m)
    return m if m in VALID_UI_MODES else "gui"


class UIEngine:
    """
    Dual-UI rendering engine managing GUI and TUI backends, widget tree,
    focus routing, dirty-region partial redraws, and live mode/theme switching.
    """

    def __init__(self, board, theme_manager=None, config=None, mode=None):
        self.board = board
        self.config = config
        self.theme_manager = theme_manager
        self.widgets = []
        self._focus_idx = -1
        self._needs_full_clear = True
        self.last_render_full = False
        self.last_drawn_count = 0

        if mode is not None:
            initial_mode = normalize_ui_mode(mode)
        elif config is not None:
            initial_mode = normalize_ui_mode(config.get("ui_mode", "gui"))
        else:
            initial_mode = "gui"

        self.mode = initial_mode
        self.backend = self._make_backend(self.mode)

        if self.theme_manager is not None:
            self.theme_manager.register_listener(self._on_theme_changed)
            if self.board is not None and hasattr(self.board, "set_lut"):
                try:
                    self.board.set_lut(self.theme_manager.active.lut)
                except Exception:
                    pass

    def _make_backend(self, mode):
        if mode == "tui":
            return TUIBackend(self.board)
        return GUIBackend(self.board)

    @property
    def theme(self):
        if self.theme_manager is not None:
            return self.theme_manager.active
        from core.theme import Theme, BUILTIN_FALLBACK_THEME
        return Theme(BUILTIN_FALLBACK_THEME)

    @property
    def mode_badge(self):
        return self.backend.mode_badge if self.backend is not None else self.mode.upper()

    def _on_theme_changed(self, _new_theme):
        self.mark_all_dirty(full_clear=True)

    def set_mode(self, mode, persist=True):
        """Switch rendering backend between 'gui' and 'tui' with deterministic cleanup."""
        target = normalize_ui_mode(mode)
        if target == self.mode and self.backend is not None:
            return self.mode

        self.backend = None
        gc.collect()
        self.mode = target
        self.backend = self._make_backend(target)

        if persist and self.config is not None:
            try:
                self.config.set("ui_mode", target, save_now=True)
            except Exception:
                pass

        self.mark_all_dirty(full_clear=True)
        gc.collect()
        return self.mode

    def toggle_mode(self, persist=True):
        """Toggle between GUI and TUI modes and persist setting."""
        nxt = "tui" if self.mode == "gui" else "gui"
        return self.set_mode(nxt, persist=persist)

    def cycle_theme(self, step=1, persist=True):
        """Cycle to the next theme via ThemeManager and mark active view dirty."""
        if self.theme_manager is None:
            return self.theme
        t = self.theme_manager.cycle(step=step, persist=persist)
        self.mark_all_dirty(full_clear=True)
        return t

    def add_widget(self, widget):
        if widget not in self.widgets:
            self.widgets.append(widget)
            if widget.focusable and self._focus_idx < 0:
                self._focus_idx = len(self.widgets) - 1
                widget.set_focus(True)
            widget.mark_dirty(full=True)
        return widget

    def remove_widget(self, widget):
        if widget in self.widgets:
            idx = self.widgets.index(widget)
            self.widgets.pop(idx)
            if self._focus_idx == idx:
                self._focus_idx = -1
                self._select_first_focusable()
            elif self._focus_idx > idx:
                self._focus_idx -= 1
            self.mark_all_dirty(full_clear=True)

    def clear_widgets(self):
        self.widgets.clear()
        self._focus_idx = -1
        self._needs_full_clear = True

    def _select_first_focusable(self):
        for i, w in enumerate(self.widgets):
            if w.focusable and w.visible:
                self._focus_idx = i
                w.set_focus(True)
                return w
        self._focus_idx = -1
        return None

    def get_focused(self):
        if 0 <= self._focus_idx < len(self.widgets):
            return self.widgets[self._focus_idx]
        return None

    def set_focus(self, widget):
        if widget not in self.widgets or not widget.focusable:
            return False
        prev = self.get_focused()
        if prev is not None and prev is not widget:
            prev.set_focus(False)
        self._focus_idx = self.widgets.index(widget)
        widget.set_focus(True)
        return True

    def mark_all_dirty(self, full_clear=True):
        if full_clear:
            self._needs_full_clear = True
        for w in self.widgets:
            w.mark_dirty(full=True)

    def render(self, force=False):
        """
        Render dirty widgets onto the board display.
        Performs a full-screen clear ONLY on initial render, mode/theme switch, or force=True.
        Otherwise only redraws dirty widgets / dirty rows for flicker-free updates.
        """
        if self.board is None or self.backend is None:
            self.last_render_full = False
            self.last_drawn_count = 0
            return 0

        theme = self.theme
        do_full = bool(force or self._needs_full_clear)
        drawn = 0

        if do_full:
            self.backend.clear_screen(theme)
            self._needs_full_clear = False

        for w in self.widgets:
            if w.draw(self.backend, theme, force=do_full):
                drawn += 1

        if do_full or drawn > 0:
            self.board.show()

        self.last_render_full = do_full
        self.last_drawn_count = drawn
        return drawn

    def handle_key(self, key, allow_hotkeys=True):
        """
        Route a key press through global Dual-UI hotkeys ([TAB]/[M] mode, [T] theme)
        or the currently focused widget.
        Returns action tag string ('mode_changed', 'theme_changed', 'handled') or None.
        """
        if not key:
            return None
        k = str(key).upper()

        if allow_hotkeys:
            if k in ("TAB", "M"):
                self.toggle_mode(persist=True)
                return "mode_changed"
            if k == "T":
                self.cycle_theme(step=1, persist=True)
                return "theme_changed"

        focused = self.get_focused()
        if focused is not None and focused.handle_key(key):
            return "handled"
        return None

    def deinit(self):
        if self.theme_manager is not None:
            self.theme_manager.unregister_listener(self._on_theme_changed)
        self.widgets.clear()
        self.backend = None
        gc.collect()

# PinhOS Phase 2 — Shared Widget & Focus Model (ui/widgets.py)
# Reusable dirty-flag widgets shared across GUI and TUI rendering backends.
# Zero full-screen framebuffers; zero hardcoded GPIO pins.


class Widget:
    """Base dirty-tracked UI widget with geometry and focus state."""

    def __init__(self, x=0, y=0, w=320, h=20, focusable=False):
        self.x = int(x)
        self.y = int(y)
        self.w = int(w)
        self.h = int(h)
        self.focusable = bool(focusable)
        self.focused = False
        self.visible = True
        self.dirty = True
        self._full_dirty = True

    def mark_dirty(self, full=True):
        self.dirty = True
        if full:
            self._full_dirty = True

    def clear_dirty(self):
        self.dirty = False
        self._full_dirty = False

    def set_bounds(self, x, y, w, h):
        nx, ny, nw, nh = int(x), int(y), int(w), int(h)
        if (nx, ny, nw, nh) != (self.x, self.y, self.w, self.h):
            self.x, self.y, self.w, self.h = nx, ny, nw, nh
            self.mark_dirty(full=True)

    def set_focus(self, focused):
        f = bool(focused) and self.focusable
        if f != self.focused:
            self.focused = f
            self.mark_dirty(full=True)

    def handle_key(self, key):
        return False

    def draw(self, backend, theme, force=False):
        if not self.visible:
            return False
        if not force and not self.dirty:
            return False
        self._render(backend, theme, full=(force or self._full_dirty))
        self.clear_dirty()
        return True

    def _render(self, backend, theme, full=True):
        pass


class StatusBar(Widget):
    """Top status bar showing OS title, UI mode badge, and right-aligned telemetry."""

    def __init__(self, x=0, y=0, w=320, h=20, title="PinhOS", mode_label="GUI", right_text=""):
        super().__init__(x, y, w, h, focusable=False)
        self.title = str(title)
        self.mode_label = str(mode_label)
        self.right_text = str(right_text)

    def update(self, title=None, mode_label=None, right_text=None):
        changed = False
        if title is not None:
            s = str(title)
            if s != self.title:
                self.title = s
                changed = True
        if mode_label is not None:
            m = str(mode_label)
            if m != self.mode_label:
                self.mode_label = m
                changed = True
        if right_text is not None:
            r = str(right_text)
            if r != self.right_text:
                self.right_text = r
                changed = True
        if changed:
            self.mark_dirty(full=True)
        return changed

    def _render(self, backend, theme, full=True):
        backend.draw_status_bar(self, theme)


class FooterBar(Widget):
    """Bottom status + hotkey bar with semantic status coloring."""

    def __init__(self, x=0, y=276, w=320, h=44, status="", status_kind="info", hints=""):
        super().__init__(x, y, w, h, focusable=False)
        self.status = str(status)
        self.status_kind = str(status_kind)
        self.hints = str(hints)

    def update(self, status=None, status_kind=None, hints=None):
        changed = False
        if status is not None:
            s = str(status)
            if s != self.status:
                self.status = s
                changed = True
        if status_kind is not None:
            k = str(status_kind)
            if k != self.status_kind:
                self.status_kind = k
                changed = True
        if hints is not None:
            h = str(hints)
            if h != self.hints:
                self.hints = h
                changed = True
        if changed:
            self.mark_dirty(full=True)
        return changed

    def _render(self, backend, theme, full=True):
        backend.draw_footer_bar(self, theme)


class Panel(Widget):
    """
    Framed telemetry / key-value panel with row-level dirty tracking.
    Rows are tuples of (label, value, color_token).
    """

    def __init__(self, x=4, y=23, w=312, h=144, title="", rows=None, label_width=102):
        super().__init__(x, y, w, h, focusable=False)
        self.title = str(title)
        self.rows = list(rows) if rows else []
        self.label_width = int(label_width)
        self._dirty_rows = set()
        self.last_redraw_rows = 0

    def set_title(self, title):
        s = str(title)
        if s != self.title:
            self.title = s
            self.mark_dirty(full=True)

    def set_rows(self, new_rows):
        """Update rows and mark only changed row indices dirty when row count matches."""
        new_list = list(new_rows)
        if len(new_list) != len(self.rows):
            self.rows = new_list
            self._dirty_rows.clear()
            self.mark_dirty(full=True)
            return True

        changed = False
        for i in range(len(new_list)):
            if new_list[i] != self.rows[i]:
                self.rows[i] = new_list[i]
                self._dirty_rows.add(i)
                changed = True
        if changed:
            self.dirty = True
        return changed

    def clear_dirty(self):
        super().clear_dirty()
        self._dirty_rows.clear()

    def _render(self, backend, theme, full=True):
        if full or not self._dirty_rows:
            self.last_redraw_rows = len(self.rows)
            backend.draw_panel(self, theme, dirty_rows=None)
        else:
            self.last_redraw_rows = len(self._dirty_rows)
            backend.draw_panel(self, theme, dirty_rows=self._dirty_rows)


class ListMenu(Widget):
    """
    Focusable scrollable list menu with dirty-row partial redraws.
    Moving selection without scrolling only redraws the 2 affected rows.
    """

    def __init__(self, x=4, y=170, w=312, h=104, title="ACTIONS", items=None, selected=0, on_select=None):
        super().__init__(x, y, w, h, focusable=True)
        self.title = str(title)
        self.items = list(items) if items else []
        self.selected = max(0, min(int(selected), max(0, len(self.items) - 1)))
        self.scroll_offset = 0
        self.on_select = on_select
        self._dirty_rows = set()
        self.last_redraw_rows = 0
        self.last_full_redraw = True

    def visible_rows(self, row_h=19, header_h=20):
        avail = max(row_h, self.h - header_h - 4)
        return max(1, avail // row_h)

    def set_items(self, items, selected=None):
        self.items = list(items) if items else []
        if selected is not None:
            self.selected = max(0, min(int(selected), max(0, len(self.items) - 1)))
        elif self.selected >= len(self.items):
            self.selected = max(0, len(self.items) - 1)
        self.scroll_offset = 0
        self._dirty_rows.clear()
        self.mark_dirty(full=True)

    def set_selected(self, index, visible_count=None):
        if not self.items:
            return False
        new_idx = int(index) % len(self.items)
        if new_idx == self.selected:
            return False

        old_idx = self.selected
        self.selected = new_idx

        vis = visible_count if visible_count is not None else self.visible_rows()
        old_scroll = self.scroll_offset
        if self.selected < self.scroll_offset:
            self.scroll_offset = self.selected
        elif self.selected >= self.scroll_offset + vis:
            self.scroll_offset = self.selected - vis + 1

        if self.scroll_offset != old_scroll:
            self._dirty_rows.clear()
            self.mark_dirty(full=True)
        else:
            self._dirty_rows.add(old_idx)
            self._dirty_rows.add(new_idx)
            self.dirty = True
        return True

    def move(self, delta, visible_count=None):
        if not self.items:
            return False
        return self.set_selected(self.selected + int(delta), visible_count=visible_count)

    def get_selected_item(self):
        if not self.items:
            return None
        return self.items[self.selected]

    def item_label(self, idx):
        item = self.items[idx]
        if isinstance(item, dict):
            return str(item.get("label", item.get("name", "")))
        return str(item)

    def item_badge(self, idx):
        item = self.items[idx]
        if isinstance(item, dict):
            b = item.get("badge")
            return str(b) if b is not None else ""
        return ""

    def handle_key(self, key):
        if not key:
            return False
        k = str(key).upper()
        if k in ("UP", "LEFT"):
            self.move(-1)
            return True
        if k in ("DOWN", "RIGHT"):
            self.move(1)
            return True
        if k in ("ENTER", "SPACE", " "):
            if callable(self.on_select) and self.items:
                self.on_select(self.selected, self.items[self.selected])
            return True
        return False

    def clear_dirty(self):
        super().clear_dirty()
        self._dirty_rows.clear()

    def _render(self, backend, theme, full=True):
        if full or not self._dirty_rows:
            self.last_full_redraw = True
            self.last_redraw_rows = min(len(self.items), self.visible_rows())
            backend.draw_list_menu(self, theme, dirty_rows=None)
        else:
            self.last_full_redraw = False
            self.last_redraw_rows = len(self._dirty_rows)
            backend.draw_list_menu(self, theme, dirty_rows=self._dirty_rows)


class ProgressBar(Widget):
    """Graphical or ASCII progress indicator (0..100%)."""

    def __init__(self, x=10, y=140, w=300, h=18, value=0, label="", color_token="accent"):
        super().__init__(x, y, w, h, focusable=False)
        self.value = max(0, min(100, int(value)))
        self.label = str(label)
        self.color_token = str(color_token)

    def set_value(self, value, label=None, color_token=None):
        changed = False
        nv = max(0, min(100, int(value)))
        if nv != self.value:
            self.value = nv
            changed = True
        if label is not None:
            nl = str(label)
            if nl != self.label:
                self.label = nl
                changed = True
        if color_token is not None:
            nc = str(color_token)
            if nc != self.color_token:
                self.color_token = nc
                changed = True
        if changed:
            self.mark_dirty(full=True)
        return changed

    def _render(self, backend, theme, full=True):
        backend.draw_progress_bar(self, theme)


class Dialog(Widget):
    """Modal overlay dialog card with title, message lines, and dismiss hint."""

    def __init__(self, x=20, y=72, w=280, h=156, title="NOTICE", lines=None, footer="[ENTER/ESC] OK", kind="info"):
        super().__init__(x, y, w, h, focusable=True)
        self.title = str(title)
        self.lines = list(lines) if lines else []
        self.footer = str(footer)
        self.kind = str(kind)

    def set_content(self, title=None, lines=None, footer=None, kind=None):
        if title is not None:
            self.title = str(title)
        if lines is not None:
            self.lines = list(lines)
        if footer is not None:
            self.footer = str(footer)
        if kind is not None:
            self.kind = str(kind)
        self.mark_dirty(full=True)

    def _render(self, backend, theme, full=True):
        backend.draw_dialog(self, theme)


class TextView(Widget):
    """Scrollable multi-line text viewer widget."""

    def __init__(self, x=4, y=24, w=312, h=248, title="", lines=None):
        super().__init__(x, y, w, h, focusable=True)
        self.title = str(title)
        self.lines = list(lines) if lines else []
        self.scroll_offset = 0

    def set_lines(self, lines, reset_scroll=True):
        self.lines = list(lines) if lines else []
        if reset_scroll:
            self.scroll_offset = 0
        self.mark_dirty(full=True)

    def visible_lines(self, line_h=12, header_h=20):
        avail = max(line_h, self.h - header_h - 6)
        return max(1, avail // line_h)

    def scroll(self, delta):
        vis = self.visible_lines()
        max_off = max(0, len(self.lines) - vis)
        new_off = max(0, min(max_off, self.scroll_offset + int(delta)))
        if new_off != self.scroll_offset:
            self.scroll_offset = new_off
            self.mark_dirty(full=True)
            return True
        return False

    def handle_key(self, key):
        if not key:
            return False
        k = str(key).upper()
        if k == "UP":
            return self.scroll(-1)
        if k == "DOWN":
            return self.scroll(1)
        return False

    def _render(self, backend, theme, full=True):
        backend.draw_text_view(self, theme)

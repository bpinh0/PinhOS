# PinhOS Phase 2 — Shared Widget & Focus Model (ui/widgets.py)
# Reusable dirty-flag widgets shared across GUI and TUI rendering backends.
# Zero full-screen framebuffers; zero hardcoded GPIO pins.


def draw_pine_logo(board, x, y, col):
    """Draw the iconic 13x14 pixel PinhOS chevron pine-tree logo using board primitives."""
    cx = int(x) + 6
    y0 = int(y)
    board.vline(cx, y0, 13, col)
    board.line(cx, y0, cx - 3, y0 + 3, col)
    board.line(cx, y0, cx + 3, y0 + 3, col)
    board.line(cx, y0 + 3, cx - 5, y0 + 8, col)
    board.line(cx, y0 + 3, cx + 5, y0 + 8, col)
    board.line(cx, y0 + 7, cx - 6, y0 + 12, col)
    board.line(cx, y0 + 7, cx + 6, y0 + 12, col)
    board.line(cx, y0 + 10, cx - 3, y0 + 13, col)
    board.line(cx, y0 + 10, cx + 3, y0 + 13, col)


def draw_wifi_icon(board, x, y, level, col_on, col_off):
    """
    Draw a crisp 13x10 pixel concentric-arc Wi-Fi fan icon (Fluke/handheld instrument style).
    level: 0=disconnected (dim + slash), 1=weak, 2=medium, 3=strong.
    """
    cx = int(x) + 6
    y0 = int(y)
    c1 = col_on if level >= 1 else col_off
    c2 = col_on if level >= 2 else col_off
    c3 = col_on if level >= 3 else col_off
    # Bottom dot (2x2)
    board.fill_rect(cx - 1, y0 + 8, 2, 2, c1)
    # Inner arc (level >= 1)
    board.hline(cx - 2, y0 + 5, 5, c1)
    board.pixel(cx - 3, y0 + 6, c1)
    board.pixel(cx + 3, y0 + 6, c1)
    # Mid arc (level >= 2)
    board.hline(cx - 3, y0 + 2, 7, c2)
    board.pixel(cx - 4, y0 + 3, c2)
    board.pixel(cx + 4, y0 + 3, c2)
    board.pixel(cx - 5, y0 + 4, c2)
    board.pixel(cx + 5, y0 + 4, c2)
    # Outer arc (level >= 3)
    board.hline(cx - 4, y0, 9, c3)
    board.pixel(cx - 5, y0 + 1, c3)
    board.pixel(cx + 5, y0 + 1, c3)
    board.pixel(cx - 6, y0 + 2, c3)
    board.pixel(cx + 6, y0 + 2, c3)
    if level <= 0:
        board.line(cx - 5, y0 + 9, cx + 5, y0, col_on)


def draw_battery_icon(board, x, y, pct, charging, col_fg, col_fill, col_bg, phase=0):
    """
    Draw a crisp 16x9 pixel handheld-instrument battery icon with proportional fill.
    When charging=True, animates a 4-phase rising charge bar (phase 0..3) + charge bolt.
    """
    x0, y0 = int(x), int(y)
    p = max(0, min(100, int(pct)))
    board.rect(x0, y0, 14, 9, col_fg)
    board.fill_rect(x0 + 14, y0 + 2, 2, 5, col_fg)
    board.fill_rect(x0 + 1, y0 + 1, 12, 7, col_bg)
    if charging:
        # Stop animation at 100% (full solid bar + static bolt); sweep 4-step below 100%
        step_w = 10 if p >= 100 else (2, 5, 8, 10)[int(phase) & 3]
        board.fill_rect(x0 + 2, y0 + 2, step_w, 5, col_fill)
        # Crisp lightning bolt overlay (contrasting against fill/bg)
        bc = col_bg if step_w >= 8 else col_fg
        board.line(x0 + 7, y0 + 1, x0 + 5, y0 + 4, bc)
        board.hline(x0 + 5, y0 + 4, 4, bc)
        board.line(x0 + 8, y0 + 4, x0 + 6, y0 + 7, bc)
    else:
        fw = (p * 10 + 50) // 100
        if fw > 0:
            board.fill_rect(x0 + 2, y0 + 2, min(10, fw), 5, col_fill)


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

    def __init__(self, x=0, y=0, w=320, h=20, title="PinhOS", mode_label="GUI", right_text="", wifi_level=None, bat_info=None, serial_link=False):
        super().__init__(x, y, w, h, focusable=False)
        self.title = str(title)
        self.mode_label = str(mode_label)
        self.right_text = str(right_text)
        self.wifi_level = wifi_level
        self.bat_info = bat_info
        self.serial_link = bool(serial_link)

    def update(self, title=None, mode_label=None, right_text=None, wifi_level="KEEP", bat_info="KEEP", serial_link="KEEP"):
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
        if wifi_level != "KEEP" and wifi_level != self.wifi_level:
            self.wifi_level = wifi_level
            changed = True
        if bat_info != "KEEP" and bat_info != self.bat_info:
            self.bat_info = bat_info
            changed = True
        if serial_link != "KEEP" and bool(serial_link) != self.serial_link:
            self.serial_link = bool(serial_link)
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



# --- Phase 3: Terminal grid widget (BusyBox shell / on-device editor) ---

# Row tag (first char of each row string) -> semantic color token.
TERM_TAG_TOKENS = {
    " ": "text",
    "e": "err",
    "c": "accent",
    "m": "text_muted",
    "o": "ok",
    "w": "warn",
    "i": "info",
}

TERM_COLS = 53  # 320px / 6px native font


class TermView(Widget):
    """
    Fixed-grid terminal viewport (53 cols of the native 6x8 font) with row-level dirty
    tracking and a block cursor. Each row is a string whose first character is a color
    tag (see TERM_TAG_TOKENS); tag 'p' draws the first `lead_cols` characters in
    `lead_token` (prompt / line-number gutter) and the remainder in the text color.
    Backends supply geometry through term_metrics(); no framebuffers are allocated.
    """

    def __init__(self, x=0, y=22, w=320, h=252, rows=None):
        super().__init__(x, y, w, h, focusable=True)
        self.rows = list(rows) if rows else []
        self.cursor = None          # (row_index, col_index) or None
        self.lead_cols = 0
        self.lead_token = "accent"
        self._dirty_rows = set()
        self.last_redraw_rows = 0

    def set_rows(self, new_rows, cursor=None):
        """Replace the visible rows; only changed rows (and cursor rows) become dirty."""
        new_list = list(new_rows)
        changed = False
        if len(new_list) != len(self.rows):
            self.rows = new_list
            self._dirty_rows.clear()
            self.cursor = cursor
            self.mark_dirty(full=True)
            return True
        for i in range(len(new_list)):
            if new_list[i] != self.rows[i]:
                self.rows[i] = new_list[i]
                self._dirty_rows.add(i)
                changed = True
        if cursor != self.cursor:
            if self.cursor is not None:
                self._dirty_rows.add(self.cursor[0])
            if cursor is not None:
                self._dirty_rows.add(cursor[0])
            self.cursor = cursor
            changed = True
        if changed:
            self.dirty = True
        return changed

    def clear_dirty(self):
        super().clear_dirty()
        self._dirty_rows.clear()

    def paint(self, board, theme, geom, bg_token, indices):
        """Draw the given row indices. geom = (x0, y0, line_h, cols, nrows, clear_x, clear_w)."""
        x0, y0, lh, cols, nrows, cx, cw = geom
        c_bg = theme.color(bg_token)
        c_txt = theme.color("text")
        c_lead = theme.color(self.lead_token)
        toff = (lh - 8) // 2
        rows = self.rows
        n = len(rows)
        for i in indices:
            if i < 0 or i >= nrows:
                continue
            ry = y0 + i * lh
            board.fill_rect(cx, ry, cw, lh, c_bg)
            if i < n:
                row = rows[i]
                tag = row[:1]
                txt = row[1:cols + 1]
                if txt:
                    if tag == "p":
                        lead = min(self.lead_cols, len(txt))
                        if lead:
                            board.text(txt[:lead], x0, ry + toff, c_lead)
                        if len(txt) > lead:
                            board.text(txt[lead:], x0 + lead * 6, ry + toff, c_txt)
                    else:
                        board.text(txt, x0, ry + toff, theme.color(TERM_TAG_TOKENS.get(tag, "text")))
            cur = self.cursor
            if cur is not None and cur[0] == i and 0 <= cur[1] < cols:
                kx = x0 + cur[1] * 6
                board.fill_rect(kx, ry, 6, lh, theme.color("accent"))
                ch = rows[i][1 + cur[1]:2 + cur[1]] if i < n else ""
                if ch and ch != " ":
                    board.text(ch, kx, ry + toff, theme.color("accent_fg"))

    def _render(self, backend, theme, full=True):
        if full or not self._dirty_rows:
            self.last_redraw_rows = len(self.rows)
            backend.draw_term_view(self, theme, dirty_rows=None)
        else:
            self.last_redraw_rows = len(self._dirty_rows)
            backend.draw_term_view(self, theme, dirty_rows=self._dirty_rows)


def layout_term_screen(mode, sb, tv, fb):
    """Apply mode-specific geometry to a StatusBar / TermView / FooterBar trio."""
    if mode == "tui":
        sb.set_bounds(0, 0, 320, 16)
        tv.set_bounds(0, 17, 320, 266)
        fb.set_bounds(0, 284, 320, 36)
    else:
        sb.set_bounds(0, 0, 320, 20)
        tv.set_bounds(0, 22, 320, 252)
        fb.set_bounds(0, 276, 320, 44)


class MosaicGrid(Widget):
    """
    Dual-layout launcher widget supporting both 3x2 GRID and 1-column LIST in both
    GUI and TUI backends, with 2-item dirty partial redraws.
    """

    def __init__(self, x=4, y=23, w=312, h=222, items=None, selected=0, cols=3, layout="grid"):
        super().__init__(x, y, w, h, focusable=True)
        self.items = list(items) if items else []
        self.cols = max(1, int(cols))
        self.layout = "list" if str(layout).lower() == "list" else "grid"
        self.selected = max(0, min(int(selected), max(0, len(self.items) - 1)))
        self._dirty_tiles = set()
        self.last_redraw_tiles = 0

    def set_layout(self, layout):
        nl = "list" if str(layout).lower() == "list" else "grid"
        if nl != self.layout:
            self.layout = nl
            self._dirty_tiles.clear()
            self.mark_dirty(full=True)
            return True
        return False

    def set_selected(self, idx):
        if not self.items:
            return False
        n = len(self.items)
        ni = int(idx) % n
        if ni == self.selected:
            return False
        self._dirty_tiles.add(self.selected)
        self._dirty_tiles.add(ni)
        self.selected = ni
        self.dirty = True
        return True

    def get_selected_item(self):
        if not self.items:
            return None
        return self.items[self.selected]

    def handle_key(self, key):
        if not key or not self.items:
            return False
        k = str(key).upper()
        n = len(self.items)
        if self.layout == "list":
            if k in ("UP", "LEFT"):
                return self.set_selected((self.selected - 1) % n)
            if k in ("DOWN", "RIGHT"):
                return self.set_selected((self.selected + 1) % n)
            return False
        c = self.cols
        if k == "LEFT":
            return self.set_selected((self.selected - 1) % n)
        if k == "RIGHT":
            return self.set_selected((self.selected + 1) % n)
        if k == "UP":
            return self.set_selected((self.selected - c) % n)
        if k == "DOWN":
            return self.set_selected((self.selected + c) % n)
        return False

    def clear_dirty(self):
        super().clear_dirty()
        self._dirty_tiles.clear()

    def _render(self, backend, theme, full=True):
        if full or not self._dirty_tiles:
            self.last_redraw_tiles = len(self.items)
            backend.draw_mosaic_grid(self, theme, dirty_tiles=None)
        else:
            self.last_redraw_tiles = len(self._dirty_tiles)
            backend.draw_mosaic_grid(self, theme, dirty_tiles=self._dirty_tiles)


class TelemetryStrip(Widget):
    """Compact dual-sparkline hardware telemetry strip (RAM free KB + CPU MHz/Temp)."""

    def __init__(self, x=4, y=245, w=312, h=28, max_samples=16):
        super().__init__(x, y, w, h, focusable=False)
        self.max_samples = int(max_samples)
        self.ram_label = "RAM ---K"
        self.cpu_label = "CPU 150M --C"
        self.ram_hist = []
        self.cpu_hist = []
        self.ok = True

    def push(self, free_kb, cpu_mhz, cpu_temp_c, ok=True):
        ram_pct = max(0, min(100, (int(free_kb) * 100) // 520))
        # Map 20..65 C die temp to 10..100% visual sparkline height
        cpu_pct = max(10, min(100, int((float(cpu_temp_c) - 18.0) * 2.2)))
        rl = "RAM {}K".format(int(free_kb))
        cl = "CPU {}M {}C".format(int(cpu_mhz), int(round(cpu_temp_c)))
        self.ram_hist.append(ram_pct)
        self.cpu_hist.append(cpu_pct)
        if len(self.ram_hist) > self.max_samples:
            self.ram_hist.pop(0)
        if len(self.cpu_hist) > self.max_samples:
            self.cpu_hist.pop(0)
        self.ram_label = rl
        self.cpu_label = cl
        self.ok = bool(ok)
        self.mark_dirty(full=True)

    def _render(self, backend, theme, full=True):
        if hasattr(backend, "draw_telemetry_strip"):
            backend.draw_telemetry_strip(self, theme)

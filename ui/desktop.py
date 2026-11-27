# PinhOS Phase 3.1 + Phase 5 — Android-Style Desktop Home, Quick-Strip Nav & [F1] Help (ui/desktop.py)
# Self-contained DesktopHome widget with LEFT/RIGHT focusable quick-category strip,
# split SYS TELEMETRY (SRAM/CPU sparklines, SWAP/BAT bars, IP + SIG/Mode + WEB ON/OFF + BL/SD),
# QUICK NOTES (/sd/pinhos/notes.txt <= 1 KB) or Theme Schema v2 custom ASCII banner,
# and [F1] Keyboard Help overlay. Zero full-screen framebuffers and zero GPIO pins.

import os
import gc
import time

from core.config import PINHOS_ROOT
from ui.widgets import Widget, Dialog, draw_styled_frame, draw_styled_bar, draw_card_header

NOTES_PATH = PINHOS_ROOT + "/notes.txt"
NOTES_MAX_BYTES = 1024

# Shared bounded sparkline rings (<= 22 small ints each, ~176 B total) so history
# survives menu/drawer/tool transitions with zero extra heap growth.
_RAM_HIST = []
_CPU_HIST = []

QUICK_STRIP = (
    ("1", "TOOL", "cat:toolkit"),
    ("2", "FILE", "cat:files"),
    ("3", "APPS", "cat:apps"),
    ("4", "SYS", "cat:system"),
    ("5", "CFG", "cat:settings"),
    ("6", "NET", "cat:set_conn"),
)

HELP_LINES = (
    "F1:Help  F2:Theme  F3:GUI/TUI  F4:Settings",
    "F5:Quick Note      ALT+F5:Reload (x2 Reset)",
    "--- SHIFT + F6..F10 (Extended Bar) ---",
    "S-F6:WebPortal ON/OFF  S-F7:COM4 Link (LNK)",
    "S-F8:Mouse (Phase 6)   S-F9:Edit notes.txt",
    "S-F10:Run 12/12 Self-Test Suite",
    "--- NAVIGATION & SHORTCUTS ---",
    "L/R:Quick Strip (1-6)  1-6:Open Category",
    "ENTER:Open Sel/Drawer  DN/ESC:Home / Back",
    "^P:Screenshot  ^L:Logs  ^V:Grid/List  ^Z:Slp",
    "^B:Sh ^F:Files ^E:Edit ^U:UART ^N:Net ^S:Mon",
)


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else int(a - b)


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _fmt_sd_bytes(num_bytes):
    if num_bytes >= 1073741824:
        return "{:.1f}G".format(num_bytes / 1073741824.0)
    if num_bytes >= 1048576:
        return "{}M".format(int(num_bytes // 1048576))
    return "{}K".format(int(num_bytes // 1024))


def show_help_dialog(board, ui):
    """
    Open the [F1] modal Help overlay listing F1-F5, Shift+F6-F10, and navigation keys.
    Dismissed cleanly via [F1], [ENTER], or [ESC] with zero SRAM leak.
    """
    if board is None or ui is None:
        return False
    dlg = Dialog(
        8, 24, 304, 248,
        title="PINHOS KEYBOARD HELP",
        lines=HELP_LINES,
        footer="[F1 / ENTER / ESC] Close Help",
        kind="info",
    )
    ui.add_widget(dlg)
    ui.render(force=False)
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            try:
                import sys as _sys
                _w = _sys.modules.get("__pinhos_wdt__")
                if _w is not None:
                    _w.feed()
                _m = _sys.modules.get("main") or _sys.modules.get("_pinhos_main")
                if _m and getattr(_m, "runtime_state", {}).get("web_active") and hasattr(_m, "step_webportal"):
                    _m.step_webportal(20)
            except Exception:
                pass
            k = poll_fn() if poll_fn else None
            if k:
                ku = str(k).upper()
                if ku in ("F1", "ENTER", "RETURN", "ESC", "SPACE", " ", "Q", "BACK", "BACKSPACE"):
                    board.beep(1100, 10)
                    break
            _sleep_ms(25)
    except KeyboardInterrupt:
        pass
    ui.remove_widget(dlg)
    ui.mark_all_dirty(True)
    board.clear_input()
    return True


def _clean_note_line(s):
    s = str(s).replace("\r", "").replace("\t", " ")
    out = []
    for ch in s:
        if " " <= ch <= "~":
            out.append(ch)
    return "".join(out).rstrip()


def load_notes(path=None, max_bytes=NOTES_MAX_BYTES):
    """Stream-read up to 1 KB from /sd/pinhos/notes.txt into clean ASCII lines."""
    p = path or NOTES_PATH
    try:
        chunks = []
        rem = int(max_bytes)
        with open(p, "rb") as f:
            while rem > 0:
                ch = f.read(min(512, rem))
                if not ch:
                    break
                chunks.append(ch)
                rem -= len(ch)
        raw = b"".join(chunks).decode("utf-8", "ignore")
    except OSError:
        return []
    except Exception:
        return []
    lines = []
    for ln in raw.split("\n"):
        cl = _clean_note_line(ln)
        if cl or lines:
            lines.append(cl)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def save_notes(lines, path=None, max_bytes=NOTES_MAX_BYTES):
    """Atomically write notes lines to /sd/pinhos/notes.txt, enforcing <= 1 KB cap."""
    p = path or NOTES_PATH
    cleaned = [_clean_note_line(ln) for ln in (lines or [])]
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    while cleaned:
        payload = ("\n".join(cleaned) + "\n").encode("utf-8")
        if len(payload) <= int(max_bytes):
            break
        if len(cleaned) == 1:
            cleaned[0] = cleaned[0][:max(1, int(max_bytes) - 1)]
            payload = (cleaned[0] + "\n").encode("utf-8")
            break
        cleaned.pop(0)
    else:
        payload = b""

    tmp = p + ".tmp"
    try:
        with open(tmp, "wb") as f:
            if payload:
                f.write(payload)
                if hasattr(f, "flush"):
                    f.flush()
        try:
            os.remove(p)
        except OSError:
            pass
        os.rename(tmp, p)
        return True
    except Exception:
        try:
            with open(p, "wb") as f:
                if payload:
                    f.write(payload)
            return True
        except Exception:
            return False


def append_note(text, path=None, max_bytes=NOTES_MAX_BYTES):
    """Append a single note line to /sd/pinhos/notes.txt (<= 1 KB streaming cap)."""
    s = _clean_note_line(text).strip()
    if not s:
        return False
    lines = load_notes(path=path, max_bytes=max_bytes)
    lines.append(s)
    return save_notes(lines, path=path, max_bytes=max_bytes)


def _wrap_notes(lines, cols=23, max_rows=10):
    out = []
    for ln in (lines or []):
        s = str(ln)
        if not s:
            out.append("")
        else:
            for i in range(0, len(s), cols):
                out.append(s[i:i + cols])
        if len(out) >= max_rows:
            break
    return out[:max_rows]


class DesktopHome(Widget):
    """
    Desktop Home Workspace Widget (320x252 body between StatusBar & FooterBar):
    - Top Quick Category Strip ([1] TOOL .. [6] NET) with LEFT/RIGHT partial-redraw focus
    - Left Split Card: SYS TELEMETRY (SRAM/CPU sparklines, SWAP/BAT bars, IP, SIG/Mode, WEB, BL/SD)
    - Right Split Card: QUICK NOTES (/sd/pinhos/notes.txt <= 1 KB) or Theme Schema v2 banner
    - Bottom App Drawer Callout Bar ([ENTER] App Drawer / Open Selected Category)
    """

    def __init__(self, x=0, y=22, w=320, h=252, notes_path=None):
        super().__init__(x, y, w, h, focusable=True)
        self.notes_path = notes_path or NOTES_PATH
        self.strip_sel = None  # None (unselected / App Drawer focus) or 0..5
        self._strip_dirty = False
        self._telem_dirty = False
        self.last_partial_strip = False
        self.last_partial_telem = False
        self._prev_telem = {}
        self.ram_hist = _RAM_HIST
        self.cpu_hist = _CPU_HIST
        self.max_samples = 22
        self.free_kb = 256
        self.used_kb = 64
        self.cpu_mhz = 150
        self.cpu_temp = 28.0
        self.cpu_pct = 0
        self.ram_warn_pct = 40
        self.ram_crit_pct = 25
        self.cpu_warn_pct = 50
        self.cpu_crit_pct = 80
        self.bat_warn_pct = 25
        self.bat_crit_pct = 10
        self.bat_pct = 100
        self.bat_mv = 4150
        self.bat_chg = False
        self.swap_used_kb = 0
        self.swap_max_kb = 512
        self.swap_pct = 0
        self.wifi_ok = False
        self.wifi_ip = "Offline"
        self.wifi_rssi = 0
        self.web_on = False
        self.lcd_bl = 80
        self.sd_free_lbl = "N/A"
        self._sd_cache_ms = 0
        self.ui_mode = "GUI"
        self.drawer_layout = "GRID"
        self.stabilized = True
        self.notes = []
        self.reload_notes()

    def set_strip_sel(self, idx):
        """Set quick-category strip focus (None or 0..5) and mark only strip/callout dirty."""
        nxt = None if idx is None else (int(idx) % len(QUICK_STRIP))
        if nxt == self.strip_sel:
            return False
        self.strip_sel = nxt
        self._strip_dirty = True
        self.mark_dirty(full=False)
        return True

    def cycle_strip(self, step=1):
        """Cycle quick-category pill selection across 0..5 with wrap-around."""
        n = len(QUICK_STRIP)
        if self.strip_sel is None:
            nxt = 0 if int(step) >= 0 else (n - 1)
        else:
            nxt = (self.strip_sel + int(step)) % n
        return self.set_strip_sel(nxt)

    def get_selected_action(self):
        """Return target action ID ('cat:toolkit'..'cat:set_conn') when a pill is highlighted, else None."""
        if self.strip_sel is not None and 0 <= self.strip_sel < len(QUICK_STRIP):
            return QUICK_STRIP[self.strip_sel][2]
        return None

    def handle_key(self, key):
        if not key:
            return False
        k = str(key).upper()
        if k == "LEFT":
            return self.cycle_strip(-1)
        if k == "RIGHT":
            return self.cycle_strip(1)
        if k == "UP" and self.strip_sel is None:
            return self.set_strip_sel(0)
        if k == "DOWN" and self.strip_sel is not None:
            return self.set_strip_sel(None)
        return False

    def clear_dirty(self):
        super().clear_dirty()
        self._strip_dirty = False
        self._telem_dirty = False

    def reload_notes(self):
        self.notes = load_notes(path=self.notes_path)
        self.mark_dirty(full=True)
        return self.notes

    def add_note(self, text):
        ok = append_note(text, path=self.notes_path)
        if ok:
            self.reload_notes()
        return ok

    def _refresh_sd_cache(self, board, force=False):
        now = _ticks_ms()
        if (not force) and self._sd_cache_ms != 0 and _ticks_diff(now, self._sd_cache_ms) < 60000:
            return
        self._sd_cache_ms = now or 1
        try:
            if board is not None and hasattr(board, "is_sd_mounted") and not board.is_sd_mounted("/sd"):
                self.sd_free_lbl = "N/A"
                return
            st = os.statvfs("/sd")
            bs = int(st[1] or st[0])
            self.sd_free_lbl = _fmt_sd_bytes(bs * int(st[3]))
        except Exception:
            self.sd_free_lbl = "N/A"

    def sync_telemetry(self, board, ui_mode="GUI", drawer_layout="GRID", stabilized=True, wifi_st=None, web_active=None, cpu_pct=None, cfg=None):
        free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        used_b = gc.mem_alloc() if hasattr(gc, "mem_alloc") else 65536
        fk, uk = free_b // 1024, used_b // 1024
        self.free_kb = fk
        self.used_kb = uk
        if cfg is not None:
            try:
                rw = max(10, min(90, int(cfg.get("ram_warn_pct", 40))))
                rc = max(5, min(rw - 5, int(cfg.get("ram_crit_pct", 25))))
                cw = max(10, min(90, int(cfg.get("cpu_warn_pct", 50))))
                cc = max(cw + 5, min(99, int(cfg.get("cpu_crit_pct", 80))))
                self.ram_warn_pct, self.ram_crit_pct = rw, rc
                self.cpu_warn_pct, self.cpu_crit_pct = cw, cc
                bw = max(10, min(60, int(cfg.get("bat_warn_pct", 25))))
                bc = max(5, min(bw - 5, int(cfg.get("bat_crit_pct", 10))))
                self.bat_warn_pct, self.bat_crit_pct = bw, bc
            except Exception:
                pass
        # Store fine-grained free RAM (0.1% of total heap, portable across boards) & CPU usage (0.1%)
        ram_free_x10 = (free_b * 1000) // max(1, free_b + used_b)
        self.ram_hist.append(ram_free_x10)
        if len(self.ram_hist) > self.max_samples:
            self.ram_hist.pop(0)

        try:
            import machine
            self.cpu_mhz = machine.freq() // 1000000
        except Exception:
            self.cpu_mhz = 150
        self.cpu_temp = board.get_cpu_temp_c() if board else 28.0
        if cpu_pct is not None:
            self.cpu_pct = max(0, min(100, int(cpu_pct)))
        self.cpu_hist.append(self.cpu_pct * 10)
        if len(self.cpu_hist) > self.max_samples:
            self.cpu_hist.pop(0)

        bat = board.get_battery() if board else {"percent": 100, "voltage_mv": 4150, "charging": False}
        self.bat_pct = int(bat.get("percent", 100))
        self.bat_mv = int(bat.get("voltage_mv", 4150))
        self.bat_chg = bool(bat.get("charging", False))
        self.lcd_bl = int(board.get_backlight()) if (board and hasattr(board, "get_backlight")) else 80
        self._refresh_sd_cache(board)

        try:
            from core.swap import get_swap_manager
            sw = get_swap_manager().stats()
            self.swap_used_kb = int(sw.get("used_kb", 0))
            self.swap_max_kb = int(sw.get("max_kb", 512))
            self.swap_pct = int(sw.get("pct", 0))
        except Exception:
            pass

        if wifi_st is None:
            try:
                from net.wifi import get_wifi_manager
                wifi_st = get_wifi_manager().status()
            except Exception:
                wifi_st = None
        if isinstance(wifi_st, dict) and wifi_st.get("connected"):
            self.wifi_ok = True
            self.wifi_ip = str(wifi_st.get("ip", "0.0.0.0"))[:15]
            self.wifi_rssi = int(wifi_st.get("rssi", 0))
        else:
            self.wifi_ok = False
            self.wifi_ip = "Offline"
            self.wifi_rssi = 0

        if web_active is not None:
            self.web_on = bool(web_active)
        else:
            w_on = False
            try:
                import sys as _sys
                _mm = _sys.modules.get("main") or _sys.modules.get("_pinhos_main")
                _rs = getattr(_mm, "runtime_state", {}) if _mm else {}
                _ws = _rs.get("web_server")
                w_on = bool(_rs.get("web_active") or (_ws is not None and getattr(_ws, "running", False)))
            except Exception:
                w_on = False
            self.web_on = w_on

        self.ui_mode = str(ui_mode).upper()
        new_layout = str(drawer_layout).upper()
        if new_layout != self.drawer_layout:
            self.drawer_layout = new_layout
            self._strip_dirty = True
        self.stabilized = bool(stabilized)
        self._telem_dirty = True
        self.mark_dirty(full=False)

    def _draw_quick_strip(self, b, theme, is_tui):
        c_bg = theme.color("bg")
        c_surf = theme.color("bg" if is_tui else "surface")
        c_bdr = theme.color("border")
        c_foc = theme.color("border_focus", default="accent")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")
        strip_style = theme.style_token("quick_strip", "pills") if hasattr(theme, "style_token") else "pills"
        bdr_style = theme.style_token("border_style", "single") if hasattr(theme, "style_token") else "single"

        sy = self.y + 2
        sh = 19
        cw = 50
        gap = 2
        sx = self.x + 5

        b.fill_rect(self.x, self.y, self.w, 23, c_bg)
        is_tabs = (strip_style == "tabs") and (not is_tui)
        if is_tabs:
            b.hline(self.x + 4, sy + sh - 1, self.w - 8, c_bdr)

        for idx, (num, lbl, _act) in enumerate(QUICK_STRIP):
            is_sel = (idx == self.strip_sel)
            tag = "{}:{}".format(num, lbl)
            tx = sx + max(2, (cw - len(tag) * 6) // 2)
            if is_tabs:
                b.fill_rect(sx, sy, cw, sh - 1, c_sbg if is_sel else c_surf)
                b.hline(sx, sy, cw, c_foc if is_sel else c_bdr)
                if is_sel:
                    b.hline(sx, sy + 1, cw, c_foc)
                b.vline(sx, sy, sh, c_foc if is_sel else c_bdr)
                b.vline(sx + cw - 1, sy, sh, c_foc if is_sel else c_bdr)
            else:
                if is_sel:
                    b.fill_rect(sx, sy, cw, sh, c_sbg)
                    b.rect(sx, sy, cw, sh, c_foc)
                else:
                    if not is_tui:
                        b.fill_rect(sx, sy, cw, sh, c_surf)
                    draw_styled_frame(b, sx, sy, cw, sh, c_bdr, bg_col=c_bg, style=bdr_style)
            if is_sel:
                b.text(tag, tx, sy + 6, c_sfg)
            else:
                b.text(num, tx, sy + 6, c_acc)
                b.text(":" + lbl, tx + 6, sy + 6, c_txt)
            sx += cw + gap

    def _draw_callout(self, b, theme, is_tui, cy, ch):
        c_bg = theme.color("bg")
        c_surf = theme.color("bg" if is_tui else "surface")
        c_acc = theme.color("accent")
        c_foc = theme.color("border_focus", default="accent")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")
        bdr_style = theme.style_token("border_style", "single") if hasattr(theme, "style_token") else "single"

        ay = cy + ch + 4
        ah = max(16, (self.y + self.h) - ay - 2)
        b.fill_rect(self.x, ay - 2, self.w, (self.y + self.h) - (ay - 2), c_bg)

        if self.strip_sel is not None and 0 <= self.strip_sel < len(QUICK_STRIP):
            num, lbl, _ = QUICK_STRIP[self.strip_sel]
            call_txt = "[ENT] Open {}:{} | [DN/ESC] App Drawer".format(num, lbl)
            b.fill_rect(self.x + 4, ay, self.w - 8, ah, c_surf)
            draw_styled_frame(b, self.x + 4, ay, self.w - 8, ah, c_foc, bg_col=c_bg, style=bdr_style)
            fg = c_acc
        else:
            call_txt = "[ENT] App Drawer ({}) | [L/R] Cat | [F1] Help".format(self.drawer_layout)
            b.fill_rect(self.x + 4, ay, self.w - 8, ah, c_surf if not is_tui else c_bg)
            draw_styled_frame(b, self.x + 4, ay, self.w - 8, ah, c_acc, bg_col=c_bg, style=bdr_style)
            fg = c_acc if not (self.focused and is_tui) else c_sfg
            if is_tui and self.focused:
                b.fill_rect(self.x + 5, ay + 1, self.w - 10, ah - 2, c_sbg)

        cx_t = self.x + max(8, (self.w - len(call_txt) * 6) // 2)
        b.text(call_txt[:50], cx_t, ay + max(2, (ah - 8) // 2), fg)

    def _draw_telem_row(self, b, key, text, x, y, w, col, c_surf, full):
        val = (text, col)
        if (not full) and self._prev_telem.get(key) == val:
            return
        self._prev_telem[key] = val
        if not full:
            b.fill_rect(x - 1, y, w, 9, c_surf)
        b.text(text, x, y, col)

    def _draw_telemetry_body(self, b, theme, is_tui, lx, cy, lw, ch, full=True):
        c_bg = theme.color("bg")
        c_surf = theme.color("bg" if is_tui else "surface")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_mut = theme.color("text_muted")
        c_ok = theme.color("ok")
        c_inf = theme.color("info")
        c_wrn = theme.color("warn")
        c_err = theme.color("err")
        bar_style = theme.style_token("bar_style", "solid") if hasattr(theme, "style_token") else "solid"
        row_w = lw - 10

        def _draw_dyn_spark(hist, x, y, w, h, warn_th, err_th, min_span, low_is_bad=False):
            if full:
                b.fill_rect(x, y, w, h, c_bg)
                b.rect(x, y, w, h, c_bdr)
            else:
                b.fill_rect(x + 1, y + 1, w - 2, h - 2, c_bg)
            if not hist:
                return
            lo, hi = min(hist), max(hist)
            span = max(min_span, hi - lo)
            pad = max(1, span // 4)
            base = max(0, lo - pad)
            rng = max(1, (hi + pad) - base)
            bw = max(3, (w - 4) // max(1, self.max_samples))
            max_bh = h - 4
            for i, v in enumerate(hist):
                bh = max(2, min(max_bh, ((v - base) * max_bh) // rng))
                bx = x + 2 + i * bw
                if bx + bw <= x + w - 1:
                    if low_is_bad:
                        col = c_err if v < err_th else (c_wrn if v < warn_th else c_ok)
                    else:
                        col = c_err if v >= err_th else (c_wrn if v >= warn_th else c_ok)
                    b.fill_rect(bx, y + h - 2 - bh, max(1, bw - 1), bh, col)

        # SRAM text + dynamic Y-axis 20px sparkline (configurable free % thresholds)
        y0 = cy + 18
        _rfp = (self.ram_hist[-1] // 10) if self.ram_hist else 0
        self._draw_telem_row(b, "sram", "SRAM {}K/{}K {}%".format(self.free_kb, self.used_kb, _rfp)[:23], lx + 6, y0, row_w, c_inf, c_surf, full)
        sp_x, sp_y, sp_w, sp_h = lx + 6, y0 + 9, lw - 12, 20
        _draw_dyn_spark(self.ram_hist, sp_x, sp_y, sp_w, sp_h, self.ram_warn_pct * 10, self.ram_crit_pct * 10, 30, low_is_bad=True)

        # CPU MHz + Temp + Usage % + dynamic Y-axis 20px sparkline (configurable CPU % thresholds)
        y1 = sp_y + sp_h + 3
        temp_i = int(round(self.cpu_temp))
        self._draw_telem_row(b, "cpu", "CPU {}MHz {}C {}%".format(self.cpu_mhz, temp_i, self.cpu_pct)[:23], lx + 6, y1, row_w, c_txt, c_surf, full)
        csp_y, csp_h = y1 + 9, 20
        _draw_dyn_spark(self.cpu_hist, sp_x, csp_y, sp_w, csp_h, self.cpu_warn_pct * 10, self.cpu_crit_pct * 10, 80, low_is_bad=False)

        # SD Swap usage bar
        y_sw = csp_y + csp_h + 4
        sw_lbl = "SWAP {}K/{}K".format(self.swap_used_kb, self.swap_max_kb) if self.swap_max_kb > 0 else "SWAP OFF"
        self._draw_telem_row(b, "swap", sw_lbl[:23], lx + 6, y_sw, row_w, c_acc if self.swap_max_kb > 0 else c_mut, c_surf, full)
        sw_bar_key = (self.swap_pct, c_acc if self.swap_pct < 80 else c_wrn, bar_style)
        if full or self._prev_telem.get("sw_bar") != sw_bar_key:
            self._prev_telem["sw_bar"] = sw_bar_key
            draw_styled_bar(b, lx + 6, y_sw + 9, lw - 12, 7, self.swap_pct, sw_bar_key[1], c_bg, c_bdr, style=bar_style, is_tui=is_tui)

        # Battery % + Voltage bar (configurable green / amber / red thresholds)
        y2 = y_sw + 19
        bat_lbl = "BAT {}% {}".format(self.bat_pct, "CHG" if self.bat_chg else "{:.1f}V".format(self.bat_mv / 1000.0))
        bat_col = c_ok if self.bat_chg else (c_err if self.bat_pct <= self.bat_crit_pct else (c_wrn if self.bat_pct <= self.bat_warn_pct else c_ok))
        self._draw_telem_row(b, "bat", bat_lbl[:23], lx + 6, y2, row_w, bat_col, c_surf, full)
        bat_bar_key = (self.bat_pct, bat_col, bar_style)
        if full or self._prev_telem.get("bat_bar") != bat_bar_key:
            self._prev_telem["bat_bar"] = bat_bar_key
            draw_styled_bar(b, lx + 6, y2 + 9, lw - 12, 7, self.bat_pct, bat_col, c_bg, c_bdr, style=bar_style, is_tui=is_tui)

        # Simultaneous Status Rows below Battery Bar (Row 1: IP, Row 2: SIG/GUARD + Mode, Row 3: WEB, Row 4: BL/SD)
        if full:
            b.hline(lx + 4, y2 + 19, lw - 8, c_bdr)
        y3 = y2 + 23
        wf_lbl = "IP: {}".format(self.wifi_ip) if self.wifi_ok else "Offline"
        self._draw_telem_row(b, "ip", wf_lbl[:23], lx + 6, y3, row_w, c_ok if self.wifi_ok else c_mut, c_surf, full)

        y4 = y3 + 12
        if self.wifi_ok and self.wifi_rssi:
            sig_lbl = "SIG {}dBm | {}".format(self.wifi_rssi, self.ui_mode)
        else:
            sig_lbl = "GUARD {} | {}".format("OK" if self.stabilized else "ARM", self.ui_mode)
        self._draw_telem_row(b, "sig", sig_lbl[:23], lx + 6, y4, row_w, c_mut, c_surf, full)

        y5 = y4 + 12
        self._draw_telem_row(b, "web", "WEB ON [S-F6]" if self.web_on else "WEB OFF [S-F6]", lx + 6, y5, row_w, c_ok if self.web_on else c_mut, c_surf, full)

        y6 = y5 + 12
        if y6 + 10 <= cy + ch:
            bl_sd = "BL:{}% | SD:{}".format(self.lcd_bl, self.sd_free_lbl)
            self._draw_telem_row(b, "bl_sd", bl_sd[:23], lx + 6, y6, row_w, c_mut, c_surf, full)

    def _render(self, backend, theme, full=True):
        b = backend.board
        is_tui = (getattr(backend, "mode", "gui") == "tui")
        cy = self.y + 25
        ch = max(140, self.h - 50)
        lw = 154
        rw = 154
        lx = self.x + 4
        rx = self.x + 162

        if (not full) and (self._strip_dirty or self._telem_dirty):
            self.last_partial_strip = bool(self._strip_dirty)
            self.last_partial_telem = bool(self._telem_dirty)
            if self._strip_dirty:
                self._draw_quick_strip(b, theme, is_tui)
                self._draw_callout(b, theme, is_tui, cy, ch)
            if self._telem_dirty:
                self._draw_telemetry_body(b, theme, is_tui, lx, cy, lw, ch, full=False)
            return

        self.last_partial_strip = False
        self.last_partial_telem = False
        self._prev_telem.clear()
        c_bg = theme.color("bg")
        c_surf = theme.color("bg" if is_tui else "surface")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_mut = theme.color("text_muted")
        bdr_style = theme.style_token("border_style", "single") if hasattr(theme, "style_token") else "single"
        hdr_style = theme.style_token("card_header", "filled") if hasattr(theme, "style_token") else "filled"

        b.fill_rect(self.x, self.y, self.w, self.h, c_bg)

        # 1. Top Quick Category Strip
        self._draw_quick_strip(b, theme, is_tui)

        # 2. Split Home Cards (y = self.y + 25 .. self.y + 227, ch = 202)
        # --- Left Card: SYS TELEMETRY ---
        b.fill_rect(lx, cy, lw, ch, c_surf)
        draw_card_header(b, lx, cy, lw, 15, "SYS TELEMETRY", theme, style=hdr_style, is_tui=is_tui)
        draw_styled_frame(b, lx, cy, lw, ch, c_bdr, bg_col=c_bg, style=bdr_style)
        self._draw_telemetry_body(b, theme, is_tui, lx, cy, lw, ch, full=True)

        # --- Right Card: QUICK NOTES or Theme Schema v2 Custom Banner ---
        banner_lines = getattr(theme, "banner_lines", ())
        b.fill_rect(rx, cy, rw, ch, c_surf)
        if banner_lines:
            draw_card_header(b, rx, cy, rw, 15, theme.name[:16], theme, style=hdr_style, right_tag="[F5]", is_tui=is_tui)
        else:
            draw_card_header(b, rx, cy, rw, 15, "QUICK NOTES", theme, style=hdr_style, right_tag="[F5]", is_tui=is_tui)
        draw_styled_frame(b, rx, cy, rw, ch, c_bdr, bg_col=c_bg, style=bdr_style)

        ny = cy + 21
        max_note_rows = max(1, (ch - 38) // 13)
        if banner_lines:
            for ln in banner_lines[:max_note_rows]:
                b.text(str(ln)[:23], rx + 6, ny, c_acc)
                ny += 13
        else:
            wrapped = _wrap_notes(self.notes, cols=23, max_rows=max_note_rows)
            if not wrapped:
                b.text("(No notes saved)", rx + 6, ny, c_mut)
                b.text("Press [F5] quick add", rx + 6, ny + 16, c_txt)
                b.text("Press [S-F9] editor", rx + 6, ny + 30, c_txt)
                b.text("/sd/pinhos/notes.txt", rx + 6, ny + 48, c_mut)
            else:
                for ln in wrapped:
                    b.text(ln, rx + 6, ny, c_txt)
                    ny += 13

        b.hline(rx + 4, cy + ch - 15, rw - 8, c_bdr)
        b.text("{} ln | <=1KB SD".format(len(self.notes))[:23], rx + 6, cy + ch - 11, c_mut)

        # 3. Bottom App Drawer Callout Strip
        self._draw_callout(b, theme, is_tui, cy, ch)

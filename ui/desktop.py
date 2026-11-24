# PinhOS Phase 3.1 — Android-Style Desktop Home Workspace & Quick Notes (ui/desktop.py)
# Self-contained DesktopHome widget with top quick-category strip, split SYS TELEMETRY
# (live SRAM sparkline, CPU/temp, battery, Wi-Fi) & QUICK NOTES (/sd/pinhos/notes.txt <= 1 KB).
# Works cleanly in both GUI and TUI modes with zero full-screen framebuffers and zero GPIO pins.

import os
import gc

from core.config import PINHOS_ROOT
from ui.widgets import Widget

NOTES_PATH = PINHOS_ROOT + "/notes.txt"
NOTES_MAX_BYTES = 1024

QUICK_STRIP = (
    ("1", "TOOL", "cat:toolkit"),
    ("2", "FILE", "cat:files"),
    ("3", "APPS", "cat:apps"),
    ("4", "SYS", "cat:system"),
    ("5", "CFG", "cat:settings"),
    ("6", "NET", "cat:set_conn"),
)


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
    # Keep newest lines if total payload exceeds max_bytes
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
    Phase 3.1 Desktop Home Workspace Widget (320x252 body between StatusBar & FooterBar):
    - Top Quick Category Strip ([1] TOOL .. [6] NET)
    - Left Split Card: SYS TELEMETRY (live SRAM sparkline, CPU/temp, battery, Wi-Fi)
    - Right Split Card: QUICK NOTES (/sd/pinhos/notes.txt <= 1 KB persistent scratchpad)
    - Bottom App Drawer Callout Bar ([ENTER] App Drawer)
    """

    def __init__(self, x=0, y=22, w=320, h=252, notes_path=None):
        super().__init__(x, y, w, h, focusable=True)
        self.notes_path = notes_path or NOTES_PATH
        self.ram_hist = []
        self.cpu_hist = []
        self.max_samples = 22
        self.free_kb = 256
        self.used_kb = 64
        self.cpu_mhz = 150
        self.cpu_temp = 28.0
        self.bat_pct = 100
        self.bat_mv = 4150
        self.bat_chg = False
        self.swap_used_kb = 0
        self.swap_max_kb = 512
        self.swap_pct = 0
        self.wifi_ok = False
        self.wifi_ip = "Offline"
        self.wifi_rssi = 0
        self.ui_mode = "GUI"
        self.drawer_layout = "GRID"
        self.stabilized = True
        self.notes = []
        self.reload_notes()

    def reload_notes(self):
        self.notes = load_notes(path=self.notes_path)
        self.mark_dirty(full=True)
        return self.notes

    def add_note(self, text):
        ok = append_note(text, path=self.notes_path)
        if ok:
            self.reload_notes()
        return ok

    def sync_telemetry(self, board, ui_mode="GUI", drawer_layout="GRID", stabilized=True, wifi_st=None):
        free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        used_b = gc.mem_alloc() if hasattr(gc, "mem_alloc") else 65536
        fk, uk = free_b // 1024, used_b // 1024
        self.free_kb = fk
        self.used_kb = uk
        ram_pct = max(4, min(100, (fk * 100) // 520))
        self.ram_hist.append(ram_pct)
        if len(self.ram_hist) > self.max_samples:
            self.ram_hist.pop(0)

        try:
            import machine
            self.cpu_mhz = machine.freq() // 1000000
        except Exception:
            self.cpu_mhz = 150
        self.cpu_temp = board.get_cpu_temp_c() if board else 28.0
        cpu_pct = max(10, min(100, int((float(self.cpu_temp) - 18.0) * 2.2)))
        self.cpu_hist.append(cpu_pct)
        if len(self.cpu_hist) > self.max_samples:
            self.cpu_hist.pop(0)

        bat = board.get_battery() if board else {"percent": 100, "voltage_mv": 4150, "charging": False}
        self.bat_pct = int(bat.get("percent", 100))
        self.bat_mv = int(bat.get("voltage_mv", 4150))
        self.bat_chg = bool(bat.get("charging", False))

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

        self.ui_mode = str(ui_mode).upper()
        self.drawer_layout = str(drawer_layout).upper()
        self.stabilized = bool(stabilized)
        self.mark_dirty(full=True)

    def _draw_mini_bar(self, b, x, y, w, h, pct, col_fill, col_bg, col_bdr, is_tui=False):
        p = max(0, min(100, int(pct)))
        if is_tui:
            slots = max(4, (w // 6) - 2)
            filled = (slots * p) // 100
            b.text("[" + ("#" * filled) + ("." * (slots - filled)) + "]", x, y, col_fill)
            return
        b.fill_rect(x, y, w, h, col_bg)
        b.rect(x, y, w, h, col_bdr)
        fw = ((w - 2) * p) // 100
        if fw > 0:
            b.fill_rect(x + 1, y + 1, fw, max(1, h - 2), col_fill)

    def _render(self, backend, theme, full=True):
        b = backend.board
        is_tui = (getattr(backend, "mode", "gui") == "tui")
        c_bg = theme.color("bg")
        c_surf = theme.color("bg" if is_tui else "surface")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_afg = theme.color("accent_fg")
        c_txt = theme.color("text")
        c_mut = theme.color("text_muted")
        c_ok = theme.color("ok")
        c_inf = theme.color("info")
        c_wrn = theme.color("warn")

        b.fill_rect(self.x, self.y, self.w, self.h, c_bg)

        # 1. Top Quick Category Strip (y = self.y + 2 .. +22, 6 chips x 50px + 2px gap = 310px)
        sy = self.y + 2
        sh = 19
        cw = 50
        gap = 2
        sx = self.x + 5
        for num, lbl, _act in QUICK_STRIP:
            if not is_tui:
                b.fill_rect(sx, sy, cw, sh, c_surf)
            b.rect(sx, sy, cw, sh, c_bdr)
            tag = "{}:{}".format(num, lbl)
            tx = sx + max(2, (cw - len(tag) * 6) // 2)
            b.text(num, tx, sy + 6, c_acc)
            b.text(":" + lbl, tx + 6, sy + 6, c_txt)
            sx += cw + gap

        # 2. Split Home Cards (y = self.y + 25 .. self.y + 225, h = 200)
        cy = self.y + 25
        ch = max(140, self.h - 50)
        lw = 154
        rw = 154
        lx = self.x + 4
        rx = self.x + 162

        # --- Left Card: SYS TELEMETRY ---
        b.fill_rect(lx, cy, lw, ch, c_surf)
        b.rect(lx, cy, lw, ch, c_bdr)
        if is_tui:
            b.text("== SYS TELEMETRY ==", lx + 6, cy + 4, c_acc)
            b.hline(lx + 2, cy + 15, lw - 4, c_bdr)
        else:
            b.fill_rect(lx + 1, cy + 1, lw - 2, 16, c_acc)
            b.text("SYS TELEMETRY", lx + 6, cy + 5, c_afg)

        # SRAM text + sparkline
        y0 = cy + 19
        b.text("SRAM {}K/{}K".format(self.free_kb, self.used_kb), lx + 6, y0, c_inf)
        sp_x, sp_y, sp_w, sp_h = lx + 6, y0 + 9, lw - 12, 24
        b.fill_rect(sp_x, sp_y, sp_w, sp_h, c_bg)
        b.rect(sp_x, sp_y, sp_w, sp_h, c_bdr)
        if self.ram_hist:
            bw = max(3, (sp_w - 4) // max(1, self.max_samples))
            for i, v in enumerate(self.ram_hist):
                bh = max(2, (v * (sp_h - 4)) // 100)
                bx = sp_x + 2 + i * bw
                if bx + bw <= sp_x + sp_w - 1:
                    b.fill_rect(bx, sp_y + sp_h - 2 - bh, max(1, bw - 1), bh, c_ok if self.free_kb > 64 else c_wrn)

        # CPU MHz + Temp + sparkline (same style as SRAM)
        y1 = sp_y + sp_h + 4
        temp_i = int(round(self.cpu_temp))
        b.text("CPU {}MHz {}C".format(self.cpu_mhz, temp_i), lx + 6, y1, c_txt)
        csp_y, csp_h = y1 + 9, 24
        b.fill_rect(sp_x, csp_y, sp_w, csp_h, c_bg)
        b.rect(sp_x, csp_y, sp_w, csp_h, c_bdr)
        if self.cpu_hist:
            bw = max(3, (sp_w - 4) // max(1, self.max_samples))
            c_cpu = c_wrn if self.cpu_mhz > 150 else c_inf
            for i, v in enumerate(self.cpu_hist):
                bh = max(2, (v * (csp_h - 4)) // 100)
                bx = sp_x + 2 + i * bw
                if bx + bw <= sp_x + sp_w - 1:
                    b.fill_rect(bx, csp_y + csp_h - 2 - bh, max(1, bw - 1), bh, c_cpu)

        # SD Swap usage bar
        y_sw = csp_y + csp_h + 5
        sw_lbl = "SWAP {}K/{}K".format(self.swap_used_kb, self.swap_max_kb) if self.swap_max_kb > 0 else "SWAP OFF"
        b.text(sw_lbl[:23], lx + 6, y_sw, c_acc if self.swap_max_kb > 0 else c_mut)
        self._draw_mini_bar(b, lx + 6, y_sw + 9, lw - 12, 7, self.swap_pct, c_acc if self.swap_pct < 80 else c_wrn, c_bg, c_bdr, is_tui)

        # Battery % + Voltage
        y2 = y_sw + 20
        bat_lbl = "BAT {}% {}".format(self.bat_pct, "CHG" if self.bat_chg else "{:.1f}V".format(self.bat_mv / 1000.0))
        b.text(bat_lbl[:23], lx + 6, y2, c_ok if (self.bat_chg or self.bat_pct > 25) else c_wrn)
        self._draw_mini_bar(b, lx + 6, y2 + 9, lw - 12, 7, self.bat_pct, c_ok if self.bat_pct > 25 else c_wrn, c_bg, c_bdr, is_tui)

        # IP Address / Offline
        y3 = y2 + 20
        wf_lbl = "IP: {}".format(self.wifi_ip) if self.wifi_ok else "Offline"
        b.text(wf_lbl[:23], lx + 6, y3, c_ok if self.wifi_ok else c_mut)
        y4 = y3 + 11
        _tok = ""
        try:
            import sys as _sys
            _mm = _sys.modules.get("main") or _sys.modules.get("_pinhos_main")
            _rs = getattr(_mm, "runtime_state", {}) if _mm else {}
            _ws = _rs.get("web_server")
            if _ws is not None and getattr(_ws, "running", False):
                _tok = str(getattr(_ws, "token", ""))
        except Exception:
            _tok = ""
        if _tok:
            b.text("WEB ON [6:KEY]"[:23], lx + 6, y4, c_acc)
        elif self.wifi_ok and self.wifi_rssi:
            b.text("SIG {}dBm | {}".format(self.wifi_rssi, self.ui_mode)[:23], lx + 6, y4, c_mut)
        else:
            b.text("GUARD {} | {}".format("OK" if self.stabilized else "ARM", self.ui_mode)[:23], lx + 6, y4, c_mut)

        # --- Right Card: QUICK NOTES ---
        b.fill_rect(rx, cy, rw, ch, c_surf)
        b.rect(rx, cy, rw, ch, c_bdr)
        if is_tui:
            b.text("== QUICK NOTES ==", rx + 6, cy + 4, c_acc)
            b.hline(rx + 2, cy + 15, rw - 4, c_bdr)
        else:
            b.fill_rect(rx + 1, cy + 1, rw - 2, 16, c_acc)
            b.text("QUICK NOTES", rx + 6, cy + 5, c_afg)
            b.text("[N/E]", rx + rw - 34, cy + 5, c_afg)

        ny = cy + 22
        max_note_rows = max(1, (ch - 36) // 13)
        wrapped = _wrap_notes(self.notes, cols=23, max_rows=max_note_rows)
        if not wrapped:
            b.text("(No notes saved)", rx + 6, ny, c_mut)
            b.text("Press [N] quick add", rx + 6, ny + 16, c_txt)
            b.text("Press [E] full edit", rx + 6, ny + 30, c_txt)
            b.text("/sd/pinhos/notes.txt", rx + 6, ny + 48, c_mut)
        else:
            for ln in wrapped:
                b.text(ln, rx + 6, ny, c_txt)
                ny += 13
        b.hline(rx + 4, cy + ch - 15, rw - 8, c_bdr)
        b.text("{} ln | <=1KB SD".format(len(self.notes))[:23], rx + 6, cy + ch - 11, c_mut)

        # 3. Bottom App Drawer Callout Strip
        ay = cy + ch + 4
        ah = max(16, (self.y + self.h) - ay - 2)
        b.fill_rect(self.x + 4, ay, self.w - 8, ah, c_surf)
        b.rect(self.x + 4, ay, self.w - 8, ah, c_acc)
        call_txt = "[ENTER] App Drawer ({}) | [N] Note | [E] Edit".format(self.drawer_layout)
        cx_t = self.x + max(8, (self.w - len(call_txt) * 6) // 2)
        b.text(call_txt[:50], cx_t, ay + max(2, (ah - 8) // 2), c_acc)

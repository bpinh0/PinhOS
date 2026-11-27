# PinhOS Sandboxed Applet: 2.4 GHz Wi-Fi Spectrum Analyzer (apps/wifi_spectrum.py)
import gc
import time

try:
    import network
except ImportError:
    network = None

APP_META = {
    "id": "wifi_spectrum",
    "name": "Wi-Fi Spectrum",
    "version": "1.0.1",
    "category": "Network",
    "description": "2.4 GHz channel congestion & RSSI spectrum analyzer",
    "entry": "main",
    "min_sram": 32768,
    "min_block": 16384,
    "needs_radio": True,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": [],
}

MAX_CH = 13


def _tok(theme, name, fallback):
    if theme is not None and hasattr(theme, "color"):
        return theme.color(name)
    return fallback


def _rssi_to_h(rssi, max_h=110):
    clamped = max(-100, min(-30, rssi))
    return max(2, int(((clamped + 100) * max_h) // 70))


def _extract_key(ev):
    """Safely extract normalized key string from HAL poll_key() events."""
    if ev is None or ev is False or ev == 0 or ev == "":
        return None
    if isinstance(ev, str):
        return None if ev == "\x00" else ev.lower()
    if isinstance(ev, int):
        return chr(ev).lower() if 1 <= ev < 128 else None
    if isinstance(ev, dict):
        if ev.get("pressed") is False or ev.get("state") == 0:
            return None
        val = ev.get("key") or ev.get("char") or ev.get("name")
        return str(val).lower() if val is not None else None
    if isinstance(ev, (tuple, list)):
        # Handle (pressed, key) or (key, ...)
        if len(ev) >= 2 and isinstance(ev[0], (bool, int)) and ev[0] in (0, 1, False, True):
            if not ev[0]:
                return None  # Ignore key release
            return str(ev[1]).lower()
        return str(ev[0]).lower()
    # Object with .key / .char
    if getattr(ev, "pressed", True) is False:
        return None
    val = getattr(ev, "key", None) or getattr(ev, "char", None)
    return str(val).lower() if val is not None else str(ev).lower()


def _feed_wdt():
    try:
        import sys as _sy
        _w = _sy.modules.get("__pinhos_wdt__")
        if _w is not None:
            _w.feed()
    except Exception:
        pass


def _scan_wifi():
    if network is None:
        return [], "No network module"
    try:
        _feed_wdt()
        wlan = network.WLAN(network.STA_IF)
        if not wlan.active():
            wlan.active(True)
            time.sleep_ms(600)
        _feed_wdt()
        raw = wlan.scan()
        _feed_wdt()
        if not raw:
            time.sleep_ms(400)
            _feed_wdt()
            raw = wlan.scan()
            _feed_wdt()
        aps = []
        for item in raw:
            ssid = item[0]
            if isinstance(ssid, bytes):
                try:
                    ssid = ssid.decode("utf-8", "replace")
                except Exception:
                    ssid = str(ssid)
            if not ssid:
                ssid = "<hidden>"
            ch = int(item[2])
            rssi = int(item[3])
            sec = int(item[4]) if len(item) > 4 else 0
            aps.append((rssi, ch, ssid[:16], sec))
        aps.sort(reverse=True)
        return aps, None
    except Exception as e:
        return [], str(e)[:28]
    finally:
        gc.collect()


def _best_channel(aps):
    scores = [0] * (MAX_CH + 1)
    for rssi, ch, _, _ in aps:
        if 1 <= ch <= MAX_CH:
            weight = max(1, rssi + 105)
            for c in range(max(1, ch - 2), min(MAX_CH, ch + 2) + 1):
                scores[c] += weight // (abs(c - ch) + 1)
    best_ch = 1
    best_sc = scores[1]
    for c in (1, 6, 11):
        if scores[c] < best_sc:
            best_sc = scores[c]
            best_ch = c
    return best_ch, scores


def _draw_spectrum(board, theme, aps, view_mode, scanning, err):
    c_bg = _tok(theme, "bg", 0)
    c_surf = _tok(theme, "surface", 1)
    c_bdr = _tok(theme, "border", 2)
    c_acc = _tok(theme, "accent", 3)
    c_afg = _tok(theme, "accent_fg", 4)
    c_txt = _tok(theme, "text", 15)
    c_muted = _tok(theme, "text_muted", 6)
    c_ok = _tok(theme, "ok", 10)
    c_warn = _tok(theme, "warn", 11)
    c_err = _tok(theme, "err", 12)

    board.fill(c_bg)
    board.fill_rect(0, 0, 320, 22, c_acc)
    mode_lbl = "CH GRAPH" if view_mode == 0 else "TOP APs"
    board.text("WIFI SPECTRUM 2.4G [{}]".format(mode_lbl), 8, 7, c_afg)

    if scanning:
        board.fill_rect(40, 120, 240, 44, c_surf)
        board.rect(40, 120, 240, 44, c_acc)
        board.text("Scanning 2.4 GHz band...", 68, 138, c_txt)
        board.show()
        return

    if err:
        board.fill_rect(14, 60, 292, 60, c_surf)
        board.rect(14, 60, 292, 60, c_err)
        board.text("Scan Error:", 24, 72, c_err)
        board.text(err, 24, 92, c_txt)
    elif view_mode == 0:
        best_ch, _ = _best_channel(aps)
        board.fill_rect(8, 28, 304, 24, c_surf)
        board.rect(8, 28, 304, 24, c_bdr)
        board.text("APs:{}".format(len(aps)), 16, 36, c_txt)
        board.text("Best:CH{}".format(best_ch), 100, 36, c_ok)
        if aps:
            board.text("Peak:{}dBm".format(aps[0][0]), 196, 36, c_acc)

        gx, gy, gw, gh = 8, 58, 304, 152
        board.fill_rect(gx, gy, gw, gh, c_surf)
        board.rect(gx, gy, gw, gh, c_bdr)

        base_y = gy + gh - 20
        for dbm, lbl in ((-40, "-40"), (-65, "-65"), (-85, "-85")):
            ly = base_y - _rssi_to_h(dbm, 110)
            board.hline(gx + 26, ly, gw - 32, c_bdr)
            board.text(lbl, gx + 2, ly - 3, c_muted)

        ch_peak = [-105] * (MAX_CH + 1)
        ch_cnt = [0] * (MAX_CH + 1)
        for rssi, ch, _, _ in aps:
            if 1 <= ch <= MAX_CH:
                ch_cnt[ch] += 1
                if rssi > ch_peak[ch]:
                    ch_peak[ch] = rssi

        bar_w = 14
        step_x = 20
        start_x = gx + 38
        for ch in range(1, MAX_CH + 1):
            bx = start_x + (ch - 1) * step_x
            if ch_cnt[ch] > 0:
                bh = _rssi_to_h(ch_peak[ch], 110)
                col = c_err if ch_peak[ch] > -55 else (c_warn if ch_peak[ch] > -75 else c_ok)
                board.fill_rect(bx, base_y - bh, bar_w, bh, col)
                board.text(str(ch_cnt[ch]), bx + 3, base_y - bh - 10, c_txt)
            else:
                board.hline(bx, base_y - 1, bar_w, c_muted)

            lbl_col = c_ok if ch == best_ch else c_muted
            board.text(str(ch), bx + (3 if ch < 10 else 0), base_y + 5, lbl_col)

        board.fill_rect(8, 216, 304, 64, c_surf)
        board.rect(8, 216, 304, 64, c_bdr)
        board.text("Strongest:", 16, 222, c_acc)
        for i in range(min(3, len(aps))):
            rssi, ch, ssid, _ = aps[i]
            y = 236 + i * 14
            board.text("CH{:02d} {:4d}dBm {}".format(ch, rssi, ssid), 16, y, c_txt)
    else:
        board.fill_rect(8, 28, 304, 252, c_surf)
        board.rect(8, 28, 304, 252, c_bdr)
        board.text("CH  RSSI   SSID", 16, 36, c_acc)
        board.hline(12, 48, 296, c_bdr)
        if not aps:
            board.text("No networks found.", 20, 64, c_muted)
        else:
            for i in range(min(13, len(aps))):
                rssi, ch, ssid, sec = aps[i]
                y = 56 + i * 17
                col = c_ok if rssi > -65 else (c_warn if rssi > -80 else c_muted)
                lock = "*" if sec > 0 else " "
                board.text("{:02d} {:4d}dB {}{}".format(ch, rssi, lock, ssid), 16, y, col)

    board.fill_rect(8, 286, 304, 26, c_surf)
    board.rect(8, 286, 304, 26, c_acc)
    board.text("[R]Scan [TAB]View [ESC]Exit", 36, 295, c_txt)
    board.show()


def main(ctx):
    board = ctx.board
    theme = getattr(ctx, "theme", None)
    if board is None:
        return {"error": "no_board"}

    view_mode = 0
    _draw_spectrum(board, theme, [], view_mode, True, None)
    if hasattr(ctx, "yield_"):
        ctx.yield_(step_web=False)
    gc.collect()
    aps, err = _scan_wifi()
    if hasattr(ctx, "yield_"):
        ctx.yield_(step_web=False)
    _draw_spectrum(board, theme, aps, view_mode, False, err)
    if hasattr(board, "clear_input"):
        board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

    while True:
        _feed_wdt()
        if hasattr(ctx, "yield_"):
            ctx.yield_(step_web=False)
        ev = poll_fn() if poll_fn else None
        k_low = _extract_key(ev)
        if k_low is None:
            time.sleep_ms(30)
            continue

        if k_low in ("esc", "key_esc", "\x1b", "q", "back", "backspace"):
            break
        elif k_low in ("r", " ", "space", "enter", "key_enter", "\r", "\n"):
            _draw_spectrum(board, theme, aps, view_mode, True, None)
            if hasattr(ctx, "yield_"):
                ctx.yield_(step_web=False)
            gc.collect()
            aps, err = _scan_wifi()
            if hasattr(ctx, "yield_"):
                ctx.yield_(step_web=False)
            _draw_spectrum(board, theme, aps, view_mode, False, err)
        elif k_low in ("\t", "tab", "key_tab"):
            view_mode = 1 - view_mode
            _draw_spectrum(board, theme, aps, view_mode, False, err)

    return {"app_id": ctx.app_id, "aps_found": len(aps)}
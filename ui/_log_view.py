# PinhOS — On-Demand Log File Picker & Scrollable Viewer (ui/_log_view.py)
# Lists /sd/pinhos/logs/*.log (system.log, crash.log, web.log, ...) in a ListMenu,
# then opens the selected log in a scrollable Dual-UI TextView. Purged on exit.

import os
import gc
import time
from core.config import PINHOS_ROOT


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _fmt_sz(n):
    return "{}B".format(n) if n < 1024 else "{:.1f}K".format(n / 1024.0)


def _list_logs(log_dir):
    known = ["system.log", "crash.log", "wdt.log", "web.log"]
    extra = []
    try:
        for fn in sorted(os.listdir(log_dir)):
            if fn.endswith(".log") and fn not in known:
                extra.append(fn)
    except OSError:
        pass
    items = []
    for fn in known + extra:
        full = log_dir + "/" + fn
        try:
            sz = int(os.stat(full)[6])
            badge = _fmt_sz(sz) if sz > 0 else "empty"
        except OSError:
            badge = "none"
        items.append({"id": full, "name": fn, "label": fn, "badge": badge})
    return items


def _read_tail(path, max_lines=60):
    lines = []
    try:
        with open(path, "r") as f:
            for ln in f:
                lines.append(ln.rstrip())
                if len(lines) > max_lines:
                    lines.pop(0)
    except OSError:
        pass
    return lines


def _log_color(s):
    u = s.upper()
    if any(k in u for k in ("[ERR", "ERROR", "CRASH", "FAIL", "EXCEPTION", "TRACEBACK", "ERR ")):
        return "err"
    if any(k in u for k in ("[WARN", "WARN", "BSOD", "TIMEOUT", "STRIKE", "WDT")):
        return "warn"
    if any(k in u for k in ("OK", "PASS", "STABILIZED", "CONNECTED", "READY", "START")):
        return "ok"
    if any(k in u for k in ("[INFO", "BOOT", "WIFI", "NTP", "UI:")):
        return "info"
    return "text"


def _view_file(board, ui, fpath, fname):
    from ui.widgets import StatusBar, TextView, FooterBar
    sb = StatusBar(0, 0, 320, 20, title="Log: " + fname, mode_label=ui.mode_badge)
    tv = TextView(4, 23, 312, 250, title=fname.upper(), lines=[])
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints="UP/DN:Scr R:Reload C:Clear ESC:Back")

    def _load():
        raw = _read_tail(fpath, max_lines=60) or ["(No entries in {})".format(fname)]
        wrapped = []
        for ln in raw:
            s = str(ln).strip()
            tok = _log_color(s)
            for i in range(0, max(1, len(s)), 49):
                wrapped.append((s[i:i + 49], tok))
        tv.title = "{} ({} ln)".format(fname.upper(), len(wrapped))
        tv.set_lines(wrapped, reset_scroll=False)
        tv.scroll_offset = max(0, len(wrapped) - tv.visible_lines())
        fb.update(status="Tail: " + fpath, status_kind="warn" if "crash" in fname else "ok")

    ui.clear_widgets(); ui.add_widget(sb); ui.add_widget(tv); ui.add_widget(fb); ui.set_focus(tv)
    _load(); ui.render(force=True); board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            k = poll_fn() if poll_fn else None
            if k:
                ku = str(k).upper()
                if ku in ("ESC", "Q", "BACK", "BACKSPACE"):
                    board.beep(900, 10); break
                elif ku in ("UP", "LEFT") and tv.scroll(-2):
                    ui.render(force=False)
                elif ku in ("DOWN", "RIGHT") and tv.scroll(2):
                    ui.render(force=False)
                elif ku == "R":
                    board.beep(1400, 10); _load(); ui.render(force=True)
                elif ku == "C":
                    try:
                        with open(fpath, "w") as f:
                            f.write("")
                    except OSError:
                        pass
                    board.beep(1000, 15); _load()
                    fb.update(status="Cleared " + fname, status_kind="warn"); ui.render(force=True)
            _sleep_ms(30)
    except KeyboardInterrupt:
        pass
    gc.collect()


def open_log_viewer(board, ui, logger, kind=None):
    """Show a ListMenu of all log files in /sd/pinhos/logs/ (system, crash, web, ...)."""
    from ui.widgets import StatusBar, ListMenu, FooterBar
    log_dir = (logger.log_dir if (logger and hasattr(logger, "log_dir")) else (PINHOS_ROOT + "/logs")).rstrip("/")
    sb = StatusBar(0, 0, 320, 20, title="Logs (/sd/pinhos/logs)", mode_label=ui.mode_badge)
    lm = ListMenu(4, 24, 312, 248, title="SELECT LOG FILE", items=[], selected=0)
    fb = FooterBar(0, 276, 320, 44, status="Pick a log file to inspect", status_kind="info",
                   hints="UP/DN:Sel  ENT:View  R:Refr  ESC:Back")

    sel = 0
    def _sync(force=True):
        nonlocal sel
        its = _list_logs(log_dir)
        sel = max(0, min(sel, max(0, len(its) - 1)))
        ui.clear_widgets(); ui.add_widget(sb); ui.add_widget(lm); ui.add_widget(fb); ui.set_focus(lm)
        lm.set_items(its, selected=sel)
        ui.render(force=force)

    _sync(force=True); board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            k = poll_fn() if poll_fn else None
            if not k:
                _sleep_ms(30); continue
            ku = str(k).upper()
            if ku in ("ESC", "Q", "BACK", "BACKSPACE"):
                board.beep(900, 10); break
            elif ku in ("UP", "DOWN"):
                if ui.handle_key(ku, allow_hotkeys=False):
                    sel = lm.selected; board.beep(1100, 8); ui.render(force=False)
            elif ku == "R":
                board.beep(1300, 10); _sync(force=True)
            elif ku in ("ENTER", "SPACE", " "):
                it = lm.get_selected_item()
                if isinstance(it, dict) and it.get("id"):
                    sel = lm.selected; board.beep(1350, 12)
                    _view_file(board, ui, it["id"], it["name"])
                    _sync(force=True)
    except KeyboardInterrupt:
        pass
    gc.collect()

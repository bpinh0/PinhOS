# PinhOS v1.0.0-alpha.2 — Phase 1+2 Boot Entry, 3-Strike Crash Guard & Dual-UI Engine (main.py)
# Zero hardcoded pin numbers outside boards/.

import os
import sys
import gc
import time
import json

try:
    import builtins
except Exception:
    try:
        import __builtin__ as builtins
    except Exception:
        builtins = None

# Ensure '/sd/pinhos' is first on sys.path (ahead of '/' and '/sd')
for _p in (".", "/", "/sd/pinhos"):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

STRIKE_LIMIT = 3
BOOT_STABLE_MS = 5000

FLASH_BOOT_STATE_PATH = "/boot_state.json"
SD_BOOT_STATE_PATH = "/sd/pinhos/boot_state.json"

_DEFAULT_BOOT_STATE = {
    "boot_strikes": 0,
    "strike_limit": STRIKE_LIMIT,
    "safe_mode": False,
    "last_error": "",
    "clean_boots": 0,
    "last_boot_ts": 0,
}

# Active runtime references
runtime_state = {
    "board": None,
    "config": None,
    "logger": None,
    "swap": None,
    "sandbox": None,
    "theme": None,
    "ui": None,
    "manifest": None,
    "boot_state": None,
    "stabilized": False,
    "safe_mode": False,
}

def bp(*args):
    """
    Write diagnostic lines via board.serial_print() (zero hardcoded pins in main.py).
    """
    board = runtime_state.get("board")
    if board is None:
        try:
            from boards import get_board
            board = get_board()
            runtime_state["board"] = board
        except Exception:
            board = None
    if board is not None and hasattr(board, "serial_print"):
        board.serial_print(*args)
    else:
        print(" ".join(str(a) for a in args))


def _ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def _ticks_diff(t1, t0):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(t1, t0)
    return int(t1 - t0)


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _resolve_boot_state_paths(state_path=None):
    if state_path:
        return [state_path]
    return [FLASH_BOOT_STATE_PATH, SD_BOOT_STATE_PATH]


def load_boot_state(state_path=None):
    """
    Read persistent boot_state.json from flash (or SD fallback) prior to loading
    UI or network modules.
    """
    state = dict(_DEFAULT_BOOT_STATE)
    for path in _resolve_boot_state_paths(state_path):
        try:
            with open(path, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                state.update(loaded)
                return state
        except Exception:
            pass
    return state


def save_boot_state(state, state_path=None):
    """
    Persist boot_state.json atomically to flash (and SD mirror if mounted).
    """
    if not isinstance(state, dict):
        return False
    saved_any = False
    payload = json.dumps(state)

    for path in _resolve_boot_state_paths(state_path):
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                f.write(payload)
                if hasattr(f, "flush"):
                    f.flush()
            try:
                os.remove(path)
            except Exception:
                pass
            os.rename(tmp_path, path)
            saved_any = True
        except Exception:
            try:
                with open(path, "w") as f:
                    f.write(payload)
                saved_any = True
            except Exception:
                pass
    return saved_any


def record_boot_strike(reason="boot_start", state_path=None):
    """
    Increment persistent boot_strikes counter BEFORE mounting SD or importing
    UI/network modules. Triggers safe_mode flag if boot_strikes >= STRIKE_LIMIT.
    """
    state = load_boot_state(state_path=state_path)
    strikes = int(state.get("boot_strikes", 0)) + 1
    limit = int(state.get("strike_limit", STRIKE_LIMIT))
    state["boot_strikes"] = strikes
    state["strike_limit"] = limit
    state["safe_mode"] = bool(strikes >= limit)
    state["last_boot_ts"] = int(time.time())
    if reason and reason != "boot_start":
        state["last_error"] = str(reason)[:120]
    save_boot_state(state, state_path=state_path)
    return state


def clear_boot_strikes(state_path=None):
    """Reset boot_strikes = 0 after system uptime stabilizes (>5s) or via recovery."""
    state = load_boot_state(state_path=state_path)
    state["boot_strikes"] = 0
    state["safe_mode"] = False
    state["last_error"] = ""
    state["clean_boots"] = int(state.get("clean_boots", 0)) + 1
    save_boot_state(state, state_path=state_path)
    return state


def check_boot_stability(elapsed_ms, state_path=None):
    """
    Verify whether uptime has reached BOOT_STABLE_MS (>= 5000 ms).
    Clears boot_strikes = 0 only when threshold is met.
    """
    if int(elapsed_ms) < BOOT_STABLE_MS:
        return False
    clear_boot_strikes(state_path=state_path)
    return True


# --- Safe Recovery Mode Helpers ---

def recovery_status(state_path=None):
    """Return and print current diagnostic state in Safe Recovery Mode."""
    gc.collect()
    free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
    state = load_boot_state(state_path=state_path)
    info = {
        "mode": "SAFE_RECOVERY" if state.get("safe_mode") else "NORMAL",
        "boot_strikes": state.get("boot_strikes", 0),
        "last_error": state.get("last_error", ""),
        "clean_boots": state.get("clean_boots", 0),
        "sram_free_bytes": free_b,
    }
    bp("[RECOVERY STATUS]", json.dumps(info))
    return info


def recovery_reset_strikes(state_path=None):
    """Clear boot_strikes = 0 and exit Safe Recovery lock state."""
    st = clear_boot_strikes(state_path=state_path)
    runtime_state["safe_mode"] = False
    runtime_state["boot_state"] = st
    bp("[RECOVERY] boot_strikes reset to 0.")
    return st


def recovery_reset_config():
    """Reset /sd/pinhos/config.json to factory defaults without crashing."""
    try:
        from core.config import ConfigManager
        cfg = ConfigManager()
        cfg.reset(save_now=True)
        bp("[RECOVERY] config.json restored to defaults.")
        return True
    except Exception as e:
        bp("[RECOVERY] config reset err:", e)
        return False


def recovery_clear_swap():
    """Purge all files in /sd/pinhos/.swap/."""
    try:
        from core.swap import clear_all
        n = clear_all()
        bp("[RECOVERY] cleared", n, "swap files.")
        return n
    except Exception as e:
        bp("[RECOVERY] swap clear err:", e)
        return 0


def recovery_reboot(state_path=None):
    """Reset boot strikes and perform a clean soft reset."""
    recovery_reset_strikes(state_path=state_path)
    try:
        import machine
        machine.soft_reset()
    except Exception:
        pass


def _register_recovery_helpers():
    helpers = {
        "recovery_status": recovery_status,
        "recovery_reset_strikes": recovery_reset_strikes,
        "recovery_reset_config": recovery_reset_config,
        "recovery_clear_swap": recovery_clear_swap,
        "recovery_reboot": recovery_reboot,
    }
    if builtins is not None:
        for k, fn in helpers.items():
            try:
                setattr(builtins, k, fn)
            except Exception:
                pass
    return list(helpers.keys())


def enter_safe_recovery_mode(board=None, state=None, reason=None, state_path=None, interactive=False):
    """
    Enter Safe Recovery Mode when boot_strikes >= 3:
    - Initializes minimal display output if board is available
    - Renders diagnostic status and recovery instructions
    - Keeps USB/UART serial REPL active with recovery helper functions registered
    - When interactive=True, polls board.poll_key() so Enter resets strikes & reboots, Esc/Q exits to REPL
    """
    if state is None:
        state = load_boot_state(state_path=state_path)
    if reason:
        state["last_error"] = str(reason)[:120]
        save_boot_state(state, state_path=state_path)

    runtime_state["safe_mode"] = True
    runtime_state["boot_state"] = state
    helper_names = _register_recovery_helpers()

    if board is None:
        try:
            from boards import get_board
            board = get_board()
            runtime_state["board"] = board
        except Exception:
            board = None

    if board is not None:
        try:
            if hasattr(board, "reset_default_lut"):
                board.reset_default_lut()
            if board.get_backlight() < 40:
                board.set_backlight(80)
            # Color 4 = Blue / Color 9 = Red / Color 3 = Amber / Color 15 = White / Color 0 = Black
            board.fill(0)
            board.rect(4, 4, 312, 312, 9)
            board.fill_rect(6, 6, 308, 26, 9)
            board.text("!! PINHOS SAFE RECOVERY MODE !!", 32, 15, 15)

            strikes = state.get("boot_strikes", 3)
            limit = state.get("strike_limit", STRIKE_LIMIT)
            err_txt = str(state.get("last_error") or "Consecutive boot failures")[:36]
            free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256

            board.text("BOOT STRIKES : {} / {} (LOCKED)".format(strikes, limit), 14, 46, 3)
            board.text("FREE SRAM    : {} KB".format(free_kb), 14, 64, 15)
            board.text("LAST FAULT   :", 14, 84, 3)
            board.text("  " + err_txt, 14, 100, 15)

            board.hline(12, 122, 296, 9)
            board.text("USB / UART SERIAL REPL ACTIVE", 14, 134, 10)
            board.text("Run recovery helpers in serial REPL:", 14, 154, 15)
            board.text(" > recovery_status()", 18, 174, 3)
            board.text(" > recovery_reset_strikes()", 18, 192, 3)
            board.text(" > recovery_reset_config()", 18, 210, 3)
            board.text(" > recovery_clear_swap()", 18, 228, 3)
            board.text(" > recovery_reboot()", 18, 246, 3)

            board.fill_rect(10, 276, 300, 30, 8)
            board.rect(10, 276, 300, 30, 3)
            board.text("[ENTER] Reset Strikes  [ESC/Q] REPL", 20, 287, 15)
            board.show()
        except Exception:
            pass

    bp("<<PINHOS:SAFE_RECOVERY_MODE:strikes={}>>".format(state.get("boot_strikes", 3)))

    if interactive and board is not None:
        # Debounce & drain stale ESC/F1/ENTER key-hold events from boot splash or Boot Menu
        _sleep_ms(220)
        board.clear_input()
        poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
        if poll_fn:
            for _ in range(16):
                if poll_fn() is None:
                    break
                _sleep_ms(10)
        board.clear_input()
        ticks = 0
        try:
            while True:
                try:
                    k = poll_fn() if poll_fn else None
                except Exception as e:
                    bp("[RECOVERY_KB_ERR]", repr(e))
                    k = None
                if k:
                    ku = str(k).upper()
                    if ku in ("ENTER", "SPACE", " ", "R"):
                        board.beep(1400, 15)
                        recovery_reset_strikes(state_path=state_path)
                        return start(
                            state_path=state_path,
                            wait_for_stability=False,
                            skip_strike_increment=True,
                            interactive=True,
                        )
                    if ku in ("ESC", "Q", "BACKSPACE", "BACK"):
                        board.beep(800, 15)
                        bp("[RECOVERY] Exiting Safe Recovery screen to REPL.")
                        board.fill_rect(10, 276, 300, 30, 10)
                        board.text("REPL ACTIVE (>>>) | COM4 READY", 32, 287, 0)
                        board.show()
                        break
                ticks += 1
                if ticks >= 40:
                    ticks = 0
                    gc.collect()
                _sleep_ms(30)
        except KeyboardInterrupt:
            bp("[RECOVERY] Interrupted via COM4 Ctrl+C; returning to REPL.")
            try:
                board.fill_rect(10, 276, 300, 30, 10)
                board.text("REPL ACTIVE (>>>) | COM4 READY", 32, 287, 0)
                board.show()
            except Exception:
                pass

    return {
        "mode": "SAFE_RECOVERY",
        "strikes": state.get("boot_strikes", 3),
        "last_error": state.get("last_error", ""),
        "helpers": helper_names,
    }


def show_bsod(board, title, exc, context="", interactive=True):
    """
    Emergency Blue Screen of Death (BSOD) fault handler.
    Resets to the built-in safe factory LUT (4=BSOD Blue, 15=White, 3=Amber),
    guarantees backlight visibility, logs diagnostics to COM4, and offers 1-key recovery.
    Returns 'RECOVER', 'SAFE_MODE', or 'REPL'.
    """
    err_str = repr(exc) if exc is not None else "Unknown runtime fault"
    bp("<<PINHOS:BSOD:{}:{}>>".format(title, err_str))
    logger = runtime_state.get("logger")
    if logger is not None and isinstance(exc, Exception):
        try:
            logger.exception("BSOD:" + str(title), exc)
        except Exception:
            pass

    if board is None:
        return "REPL"

    try:
        if hasattr(board, "reset_default_lut"):
            board.reset_default_lut()
        if board.get_backlight() < 50:
            board.set_backlight(80)
        board.recover_refresh()
        board.fill(4)
        board.rect(4, 4, 312, 312, 15)
        board.fill_rect(6, 6, 308, 24, 15)
        board.text("PINHOS KERNEL / UI FAULT (BSOD)", 28, 14, 4)

        free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        board.text("FAULT  : " + str(title)[:27], 14, 42, 3)
        if context:
            board.text("CTX    : " + str(context)[:27], 14, 58, 15)
        board.text("SRAM   : {} KB FREE".format(free_kb), 14, 74, 15)
        board.hline(12, 92, 296, 15)

        board.text("EXCEPTION:", 14, 102, 3)
        y = 118
        for i in range(0, min(len(err_str), 144), 36):
            board.text(err_str[i:i + 36], 14, y, 15)
            y += 14

        board.hline(12, 240, 296, 15)
        board.text("Display LUT & Refresh Reset OK.", 14, 250, 10)
        board.fill_rect(10, 272, 300, 36, 0)
        board.rect(10, 272, 300, 36, 15)
        board.text("[ENT/R] Recover  [L] Crash Logs", 18, 280, 15)
        board.text("[F1] Safe Mode   [Q/ESC] REPL", 18, 294, 3)
        board.show()
    except Exception as draw_exc:
        bp("[BSOD_DRAW_ERR]", repr(draw_exc))

    if not interactive:
        return "REPL"

    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            k = poll_fn() if poll_fn else None
            if k:
                ku = str(k).upper()
                if ku in ("ENTER", "SPACE", " ", "R"):
                    board.beep(1400, 15)
                    return "RECOVER"
                if ku == "L":
                    board.beep(1200, 12)
                    return "LOGS"
                if ku == "F1":
                    board.beep(1000, 15)
                    return "SAFE_MODE"
                if ku in ("Q", "ESC", "BACK", "BACKSPACE"):
                    board.beep(800, 15)
                    return "REPL"
            _sleep_ms(30)
    except KeyboardInterrupt:
        return "REPL"


def open_log_viewer(board, ui, logger, kind="system"):
    """
    On-device scrollable System & Crash Log Viewer built on Dual-UI TextView.
    [UP/DN] Scroll | [TAB/S] Switch system.log/crash.log | [R] Reload | [C] Clear | [ESC/Q] Back
    """
    from ui.widgets import StatusBar, TextView, FooterBar

    cur_kind = "crash" if kind == "crash" else "system"
    sb = StatusBar(0, 0, 320, 20, title="PinhOS Logs", mode_label=ui.mode_badge)
    tv = TextView(4, 23, 312, 250, title="SYSTEM.LOG", lines=[])
    fb = FooterBar(
        0, 276, 320, 44,
        status="",
        status_kind="info",
        hints="UP/DN:Scr S:Sys/Crsh C:Clr ESC:Back",
    )

    def _format_log_line(raw_line):
        """Compact '[YYYY-MM-DD HH:MM:SS] [LEVEL] msg' -> 'HH:MM:SS L msg' for 320px display."""
        s = str(raw_line).strip()
        if len(s) > 22 and s[0] == "[" and s[11] == " " and s[20] == "]":
            hhmmss = s[12:20]
            rest = s[21:].lstrip()
            lvl = ""
            for tag, short in (("[INFO]", "I"), ("[WARN]", "W"), ("[ERROR]", "E"), ("[CRASH]", "!"), ("[DEBUG]", "D")):
                if rest.startswith(tag):
                    lvl = short
                    rest = rest[len(tag):].lstrip()
                    break
            return "{} {} {}".format(hhmmss, lvl, rest) if lvl else "{} {}".format(hhmmss, rest)
        return s

    def _word_wrap(text, width=36, cont_indent="  "):
        """Word-wrap text cleanly at spaces without splitting words."""
        if len(text) <= width:
            return [text]
        out = []
        words = text.split(" ")
        cur = ""
        limit = width
        for w in words:
            if not cur:
                if len(w) <= limit:
                    cur = w
                else:
                    # Single token longer than line width: chunk it
                    for i in range(0, len(w), limit):
                        chunk = w[i:i + limit]
                        if i + limit < len(w):
                            out.append((cont_indent if out else "") + chunk)
                        else:
                            cur = chunk
            elif len(cur) + 1 + len(w) <= limit:
                cur = cur + " " + w
            else:
                out.append((cont_indent if out else "") + cur)
                limit = width - len(cont_indent)
                cur = w
        if cur:
            out.append((cont_indent if out else "") + cur)
        return out

    def _load_lines():
        raw_lines = logger.read_tail(kind=cur_kind, max_lines=80) if logger else []
        if not raw_lines:
            raw_lines = ["(No entries in {}.log)".format(cur_kind)]
        wrapped = []
        for ln in raw_lines:
            fmt = _format_log_line(ln)
            wrapped.extend(_word_wrap(fmt, width=49))
        tv.title = "CRASH.LOG ({} ln)".format(len(wrapped)) if cur_kind == "crash" else "SYSTEM.LOG ({} ln)".format(len(wrapped))
        tv.set_lines(wrapped, reset_scroll=False)
        vis = tv.visible_lines()
        tv.scroll_offset = max(0, len(wrapped) - vis)
        theme_short = ui.theme.name.split()[0][:10]
        sb.update(title="Logs: {}.log".format(cur_kind), mode_label=ui.mode_badge, right_text=theme_short)
        fb.update(
            status="Tail: /sd/pinhos/logs/{}.log".format(cur_kind),
            status_kind="warn" if cur_kind == "crash" else "ok",
        )

    ui.clear_widgets()
    ui.add_widget(sb)
    ui.add_widget(tv)
    ui.add_widget(fb)
    ui.set_focus(tv)
    _load_lines()
    ui.render(force=True)

    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            k = poll_fn() if poll_fn else None
            if k:
                ku = str(k).upper()
                if ku in ("ESC", "Q", "BACK", "BACKSPACE"):
                    board.beep(900, 10)
                    break
                elif ku in ("UP", "LEFT"):
                    if tv.scroll(-2):
                        ui.render(force=False)
                elif ku in ("DOWN", "RIGHT"):
                    if tv.scroll(2):
                        ui.render(force=False)
                elif ku in ("S", "TAB"):
                    cur_kind = "crash" if cur_kind == "system" else "system"
                    board.beep(1300, 10)
                    _load_lines()
                    ui.render(force=True)
                elif ku == "R":
                    board.beep(1400, 10)
                    _load_lines()
                    ui.render(force=True)
                elif ku == "C":
                    if logger:
                        logger.clear_logs(kind=cur_kind)
                    board.beep(1000, 15)
                    _load_lines()
                    fb.update(status="Cleared {}.log".format(cur_kind), status_kind="warn")
                    ui.render(force=True)
            _sleep_ms(30)
    except KeyboardInterrupt:
        pass
    gc.collect()


_DASHBOARD_ACTIONS = (
    {"id": "selftest", "label": "Run On-Device Self-Test", "badge": "[F2]"},
    {"id": "hello", "label": "Sandbox: Hello PinhOS", "badge": "[1]"},
    {"id": "matrix", "label": "Sandbox: Matrix Rain", "badge": "[2]"},
    {"id": "logs", "label": "System & Crash Logs", "badge": "[L]"},
    {"id": "refresh", "label": "Refresh Telemetry & Beep", "badge": "[R]"},
)

_DASHBOARD_HINTS = "M/TAB:Mode T:Theme L:Logs Q:REPL"


def _build_telemetry_rows(board, boot_state, elapsed_ms, stabilized):
    """Collect live hardware & runtime telemetry rows for the dashboard Panel."""
    free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
    bat = board.get_battery()
    sd_stats = board.get_sd_stats()

    strikes = boot_state.get("boot_strikes", 0)
    if stabilized:
        guard_str = "STABLE (0/3 OK)"
        guard_tok = "ok"
    else:
        rem_s = max(0, (BOOT_STABLE_MS - elapsed_ms + 999) // 1000)
        guard_str = "ARMED ({}/3 - {}s)".format(strikes, rem_s)
        guard_tok = "warn"

    sd_str = "MOUNTED ({} MB)".format(sd_stats["free_kb"] // 1024) if sd_stats["mounted"] else "UNMOUNTED"
    bat_str = "{}% ({}mV{})".format(
        bat["percent"],
        bat["voltage_mv"],
        " CHG" if bat["charging"] else "",
    )
    board_label = "PicoCalc (RP2350)" if board.id == "picocalc" else board.name

    return [
        ("BOARD HAL :", board_label, "text"),
        ("DISPLAY   :", "{}x{} RGB565 LUT".format(board.display_width, board.display_height), "text"),
        ("SD STORAGE:", sd_str, "ok" if sd_stats["mounted"] else "err"),
        ("BOOT GUARD:", guard_str, guard_tok),
        ("FREE SRAM :", "{} KB / 520 KB".format(free_kb), "info"),
        ("BATTERY   :", bat_str, "text"),
        ("BACKLIGHT :", "LCD {}% / KB {}%".format(board.get_backlight(), board.get_kb_backlight()), "text"),
        ("CPU / RTC :", "{}C | {}".format(board.get_cpu_temp_c(), board.get_timestamp_str(True)), "text"),
    ], bat


def _ensure_ui_services(board, cfg=None):
    """Ensure ThemeManager and UIEngine are initialized in runtime_state."""
    theme_mgr = runtime_state.get("theme")
    ui = runtime_state.get("ui")
    if theme_mgr is None:
        from core.theme import get_theme_manager
        theme_mgr = get_theme_manager(config=cfg, board=board, force_new=True)
        runtime_state["theme"] = theme_mgr
    if ui is None:
        from ui.engine import UIEngine
        ui = UIEngine(board=board, theme_manager=theme_mgr, config=cfg)
        runtime_state["ui"] = ui
    return theme_mgr, ui


class _DashboardView:
    """Phase 2 Dual-UI Dashboard composed of reusable dirty-tracked widgets."""

    def __init__(self, ui, manifest, sel_action=0):
        from ui.widgets import StatusBar, Panel, ListMenu, FooterBar

        self.ui = ui
        self.manifest = manifest or {"version": "1.0.0-alpha.2", "arch": "armv7emsp"}
        self.status_bar = StatusBar(0, 0, 320, 20, title="PinhOS", mode_label=ui.mode_badge)
        self.telemetry_panel = Panel(4, 23, 312, 144, title="SYSTEM TELEMETRY", label_width=102)
        self.action_menu = ListMenu(
            4, 170, 312, 104,
            title="PINHOS ACTIONS",
            items=_DASHBOARD_ACTIONS,
            selected=sel_action,
        )
        self.footer_bar = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=_DASHBOARD_HINTS)

        ui.clear_widgets()
        ui.add_widget(self.status_bar)
        ui.add_widget(self.telemetry_panel)
        ui.add_widget(self.action_menu)
        ui.add_widget(self.footer_bar)
        ui.set_focus(self.action_menu)

    def sync(self, board, boot_state, elapsed_ms, stabilized, status_msg="", status_kind="info"):
        rows, bat = _build_telemetry_rows(board, boot_state, elapsed_ms, stabilized)
        ver = self.manifest.get("version", "1.0.0-alpha.2")
        theme_name = self.ui.theme.name
        right_txt = "{}%".format(bat["percent"])

        self.status_bar.update(
            title="PinhOS v{}".format(ver),
            mode_label=self.ui.mode_badge,
            right_text=right_txt,
        )
        self.telemetry_panel.set_rows(rows)
        if not status_msg:
            status_msg = "Theme: {} | Mode: {}".format(theme_name, self.ui.mode_badge)
            status_kind = "info"
        self.footer_bar.update(status=status_msg, status_kind=status_kind, hints=_DASHBOARD_HINTS)

    def render(self, force=False):
        return self.ui.render(force=force)


def ui_loop(sel_action=0):
    """
    Interactive Phase 2 Dual-UI keyboard event loop.
    Polls STM32 I2C keyboard via board.poll_key() without starving Core 1 LCD refresh,
    supports live GUI<->TUI switching ([TAB]/[M]) and theme cycling ([T]),
    and cleanly exits to REPL on [Q] or serial Ctrl+C (\\x03).
    """
    board = runtime_state.get("board")
    if board is None:
        from boards import get_board
        board = get_board()
        runtime_state["board"] = board

    if hasattr(board, "ensure_serial_repl"):
        board.ensure_serial_repl()

    if runtime_state.get("safe_mode"):
        return enter_safe_recovery_mode(
            board=board,
            state=runtime_state.get("boot_state"),
            interactive=True,
        )

    cfg = runtime_state.get("config")
    logger = runtime_state.get("logger")
    theme_mgr, ui = _ensure_ui_services(board, cfg=cfg)
    manifest = runtime_state.get("manifest") or {"version": "1.0.0-alpha.2", "arch": "armv7emsp"}
    boot_state = runtime_state.get("boot_state") or load_boot_state()
    sandbox = runtime_state.get("sandbox")
    from boards.base import MOD_ALT

    view = _DashboardView(ui, manifest, sel_action=sel_action)
    prev_crash = runtime_state.get("prev_crash")
    if prev_crash:
        status_msg = "Prev Crash ({})! Press [L] Logs".format(prev_crash.get("op", "?"))
        status_kind = "warn"
    else:
        status_msg = ""
        status_kind = "info"
    last_reload_ms = 0

    def _drain_keys(delay_ms=150):
        _sleep_ms(delay_ms)
        board.clear_input()
        pf = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
        if pf:
            for _ in range(8):
                if pf() is None:
                    break
        board.clear_input()

    def _run_action(act_id):
        nonlocal status_msg, status_kind, view
        poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

        if act_id == "selftest":
            board.beep(1400, 15)
            _drain_keys(120)
            if logger:
                logger.set_breadcrumb("SELFTEST", "run_all")
            import tests.selftest as _st
            res = _st.run_all(interactive_wait=True)
            if logger:
                logger.info("SELFTEST: {}/{} {}".format(
                    res.get("passed", 0), res.get("total", 8), "PASS" if res.get("ok") else "FAIL"
                ))
                logger.clear_breadcrumb("IDLE")
            _drain_keys(150)
            # Re-apply active theme LUT in case selftest changed it
            board.set_lut(theme_mgr.active.lut)
            status_msg = "Self-Test {}/{} {}".format(
                res.get("passed", 0), res.get("total", 8), "PASS" if res.get("ok") else "FAIL"
            )
            status_kind = "ok" if res.get("ok") else "err"
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "hello":
            board.beep(1400, 15)
            _drain_keys(120)
            if logger:
                logger.set_breadcrumb("APP", "hello_world")
            if sandbox is not None:
                res = sandbox.run_file("/sd/pinhos/apps/hello_world.py", wait_on_error=True)
                status_msg = "Hello OK (delta={}B)".format(res.get("sram_delta", 0))
                status_kind = "ok" if res.get("ok") else "err"
                if logger:
                    logger.info("APP hello_world: ok={} delta={}B".format(res.get("ok"), res.get("sram_delta", 0)))
                if res.get("ok"):
                    board.clear_input()
                    while True:
                        ak = poll_fn() if poll_fn else None
                        if ak is not None:
                            board.beep(1100, 10)
                            break
                        _sleep_ms(30)
            if logger:
                logger.clear_breadcrumb("IDLE")
            _drain_keys(150)
            board.set_lut(theme_mgr.active.lut)
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "matrix":
            board.beep(1400, 15)
            _drain_keys(120)
            if logger:
                logger.set_breadcrumb("APP", "matrix_deck")
            if sandbox is not None:
                res = sandbox.run_file("/sd/pinhos/apps/matrix_deck.py", wait_on_error=True)
                status_msg = "Matrix OK (delta={}B)".format(res.get("sram_delta", 0))
                status_kind = "ok" if res.get("ok") else "err"
                if logger:
                    logger.info("APP matrix_deck: ok={} delta={}B".format(res.get("ok"), res.get("sram_delta", 0)))
            if logger:
                logger.clear_breadcrumb("IDLE")
            _drain_keys(150)
            board.set_lut(theme_mgr.active.lut)
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "logs":
            board.beep(1400, 12)
            _drain_keys(100)
            cur_sel = view.action_menu.selected
            open_log_viewer(board, ui, logger, kind="crash" if runtime_state.get("prev_crash") else "system")
            runtime_state["prev_crash"] = None
            _drain_keys(120)
            view = _DashboardView(ui, manifest, sel_action=cur_sel)
            status_msg = "Returned from Logs"
            status_kind = "info"
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "refresh":
            board.beep(1600, 15)
            gc.collect()
            if board.get_backlight() < 40:
                board.set_backlight(80)
            board.set_lut(theme_mgr.active.lut)
            status_msg = "Display & Telemetry OK @ " + board.get_timestamp_str(True)
            status_kind = "ok"
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

    board.clear_input()
    board.set_lut(theme_mgr.active.lut)
    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
    view.render(force=True)

    idle_ticks = 0
    try:
        while True:
            poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
            key = poll_fn() if poll_fn else None
            if key:
                idle_ticks = 0
                k = str(key).upper()

                if k == "Q":
                    board.beep(800, 15)
                    if logger:
                        logger.info("UI: Clean exit to REPL (key=Q)")
                        logger.clear_breadcrumb("CLEAN_EXIT")
                    bp("[UI] Exiting Dual-UI loop to REPL (key=Q)")
                    view.footer_bar.update(
                        status="EXITED TO REPL (COM4) | _pm.ui_loop()",
                        status_kind="ok",
                        hints="REPL ACTIVE (>>>) | UART0 READY",
                    )
                    view.render(force=False)
                    break

                elif k in ("TAB", "M"):
                    ui.toggle_mode(persist=True)
                    if logger:
                        logger.info("UI: Mode -> {}".format(ui.mode_badge))
                    board.beep(1300, 12)
                    status_msg = "Switched to {} Mode ({})".format(ui.mode_badge, ui.theme.name)
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
                    view.render(force=True)

                elif k == "T":
                    new_theme = ui.cycle_theme(step=1, persist=True)
                    if logger:
                        logger.info("UI: Theme -> {}".format(new_theme.id))
                    board.beep(1500, 12)
                    status_msg = "Theme: {} [{}]".format(new_theme.name, ui.mode_badge)
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
                    view.render(force=True)

                elif k == "L":
                    _run_action("logs")

                elif k in ("UP", "DOWN", "LEFT", "RIGHT"):
                    if ui.handle_key(k, allow_hotkeys=False):
                        board.beep(1100, 8)
                        # Partial dirty-row redraw ONLY (zero full-screen clear!)
                        view.render(force=False)

                elif k in ("ENTER", "SPACE", " "):
                    item = view.action_menu.get_selected_item()
                    if isinstance(item, dict) and item.get("id"):
                        _run_action(item["id"])

                elif k == "F2":
                    _run_action("selftest")

                elif k == "1":
                    _run_action("hello")

                elif k == "2":
                    _run_action("matrix")

                elif k == "F5" and (board.get_modifiers() & MOD_ALT):
                    # ALT+F5 once = Hard Reload UI; ALT+F5 twice within 3s = hardware reset escape hatch
                    now_ms = _ticks_ms()
                    if last_reload_ms and _ticks_diff(now_ms, last_reload_ms) < 3000:
                        if logger:
                            logger.warn("UI: Double ALT+F5 hardware reset triggered")
                            logger.clear_breadcrumb("CLEAN_EXIT")
                        bp("[UI] Double ALT+F5 -> machine.reset()")
                        board.beep(900, 20)
                        try:
                            import machine
                            machine.reset()
                        except Exception:
                            pass
                    last_reload_ms = now_ms
                    bp("[UI] Hard Reload triggered (ALT+F5)")
                    if logger:
                        logger.warn("UI: Hard Reload triggered (ALT+F5)")
                    cur_sel = view.action_menu.selected
                    if hasattr(board, "reset_default_lut"):
                        board.reset_default_lut()
                    if board.get_backlight() < 50:
                        board.set_backlight(80)
                    theme_mgr.apply(theme_mgr.active.id, persist=False, notify=False)
                    ui.set_mode(ui.mode, persist=False)
                    view = _DashboardView(ui, manifest, sel_action=cur_sel)
                    gc.collect()
                    board.beep(1200, 12)
                    board.beep(1600, 15)
                    status_msg = "Reload OK [ALT+F5x2=Reboot]"
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
                    view.render(force=True)

                elif k in ("R", "F1"):
                    _run_action("refresh")

                elif k in ("ESC", "BACK", "BACKSPACE"):
                    board.beep(900, 10)
                    status_msg = "Dashboard Active (Press Q for REPL)"
                    status_kind = "info"
                    view.footer_bar.update(status=status_msg, status_kind=status_kind)
                    view.render(force=False)

            idle_ticks += 1
            if idle_ticks >= 40:
                idle_ticks = 0
                gc.collect()
            _sleep_ms(30)
    except KeyboardInterrupt:
        if hasattr(board, "init_uart_bridge"):
            board.init_uart_bridge()
        bp("[UI] Interrupted via serial Ctrl+C; returning to REPL.")
    except Exception as ui_exc:
        choice = show_bsod(
            board,
            "UI_LOOP_EXCEPTION",
            ui_exc,
            context="mode={} theme={}".format(ui.mode, theme_mgr.active.id),
            interactive=True,
        )
        if choice == "RECOVER":
            theme_mgr.apply("cyber_amber", persist=False)
            ui.set_mode("gui", persist=False)
            return ui_loop(sel_action=0)
        if choice == "LOGS":
            theme_mgr.apply("cyber_amber", persist=False)
            ui.set_mode("gui", persist=False)
            open_log_viewer(board, ui, logger, kind="crash")
            return ui_loop(sel_action=0)
        if choice == "SAFE_MODE":
            return enter_safe_recovery_mode(board=board, state=boot_state, reason=repr(ui_exc), interactive=True)
        if hasattr(board, "init_uart_bridge"):
            board.init_uart_bridge()


def _boot_progress(pct, msg, pause_ms=0, clear_splash=False):
    """Advance the frozen pinhos_boot splash progress bar if active during cold boot."""
    pb = sys.modules.get("pinhos_boot")
    if pb is not None and getattr(pb, "_splash_drawn", False) and hasattr(pb, "set_progress"):
        try:
            pb.set_progress(pct, msg)
            if pause_ms > 0:
                _sleep_ms(pause_ms)
            if clear_splash:
                pb._splash_drawn = False
        except Exception:
            pass


def start(state_path=None, simulate_fault=None, wait_for_stability=True, skip_strike_increment=False, interactive=False):
    """
    Main boot sequence (Phase 1 + Phase 2 Dual-UI Engine & Unified Theme System):
    1. Increment persistent boot_strikes in flash BEFORE mounting SD or loading modules.
    2. Enter Safe Recovery Mode immediately if boot_strikes >= 3.
    3. Initialize Board HAL, mount /sd with retry, and create canonical /sd/pinhos/ dirs.
    4. Initialize ConfigManager, Logger, SwapManager, ThemeManager, UIEngine, and SandboxRunner.
    5. Run startup stabilization window (>5s) and clear boot_strikes = 0 once stable.
    6. Optionally enter interactive Dual-UI keyboard loop (ui_loop) while keeping UART0 dupterm active.
    """
    t0 = _ticks_ms()

    # Step 1: Increment persistent boot strike counter BEFORE mounting SD or importing core/UI
    if skip_strike_increment:
        boot_state = load_boot_state(state_path=state_path)
    else:
        boot_state = record_boot_strike(reason="boot_start", state_path=state_path)
    runtime_state["boot_state"] = boot_state
    runtime_state["stabilized"] = False

    # Step 2: Check 3-Strike threshold
    if boot_state.get("boot_strikes", 0) >= int(boot_state.get("strike_limit", STRIKE_LIMIT)):
        return enter_safe_recovery_mode(state=boot_state, state_path=state_path, interactive=interactive)

    try:
        # Optional fault injection hook for automated testing
        if simulate_fault:
            raise RuntimeError(str(simulate_fault))

        # Step 3: Initialize Board HAL, persistent UART0 dupterm, & mount SD card with retry logic
        from boards import get_board
        board = get_board()
        if hasattr(board, "init_uart_bridge"):
            board.init_uart_bridge()
        board.mount_sd("/sd", retries=3)
        runtime_state["board"] = board
        _boot_progress(90, "Board HAL & SD Ready...")

        # Step 4: Initialize canonical /sd/pinhos/ filesystem hierarchy, core services & Dual-UI
        from core.config import ensure_canonical_dirs, load_version_manifest, ConfigManager
        from core.logger import get_logger
        from core.swap import get_swap_manager
        from core.sandbox import SandboxRunner
        from core.theme import get_theme_manager
        from ui.engine import UIEngine

        ensure_canonical_dirs()
        manifest = load_version_manifest()
        cfg = ConfigManager()

        # Re-sync board profile & backlights from loaded config
        desired_board = cfg.get("board", "picocalc")
        if desired_board != board.id:
            board = get_board(profile=desired_board, config=cfg.as_dict(), force_new=True)
            runtime_state["board"] = board
        board.set_backlight(cfg.get("lcd_brightness", 80))
        board.set_kb_backlight(cfg.get("kb_brightness", 60))

        # Mirror boot_state onto SD now that /sd is mounted
        if state_path is None:
            save_boot_state(boot_state)

        logger = get_logger()
        prev_crash = logger.check_previous_crash()
        runtime_state["prev_crash"] = prev_crash
        logger.set_breadcrumb("BOOT_INIT", "services")
        swap = get_swap_manager()
        swap.prune_stale()

        _boot_progress(95, "Loading Theme & Dual-UI...")
        theme_mgr = get_theme_manager(config=cfg, board=board, force_new=True)
        ui = UIEngine(board=board, theme_manager=theme_mgr, config=cfg)
        sandbox = SandboxRunner(board=board, config=cfg, swap=swap, logger=logger, theme=theme_mgr, ui=ui)

        runtime_state["manifest"] = manifest
        runtime_state["config"] = cfg
        runtime_state["logger"] = logger
        runtime_state["swap"] = swap
        runtime_state["theme"] = theme_mgr
        runtime_state["ui"] = ui
        runtime_state["sandbox"] = sandbox
        _register_recovery_helpers()

        boot_msg = "BOOT: PinhOS v{} ({}) starting on {} [{} / {}]".format(
            manifest.get("version", "1.0.0-alpha.2"),
            manifest.get("arch", "armv7emsp"),
            board.name,
            ui.mode_badge,
            theme_mgr.active.id,
        )
        logger.info(boot_msg)
        bp("[BOOT]", boot_msg)
        _boot_progress(100, "PinhOS Ready!", pause_ms=180, clear_splash=True)

        # Step 5: Render initial Dual-UI dashboard and monitor 5-second stability window
        view = _DashboardView(ui, manifest, sel_action=0)
        elapsed = _ticks_diff(_ticks_ms(), t0)
        view.sync(board, boot_state, elapsed, False)
        view.render(force=True)

        if wait_for_stability:
            last_draw_s = -1
            while True:
                now = _ticks_ms()
                elapsed = _ticks_diff(now, t0)
                if check_boot_stability(elapsed, state_path=state_path):
                    boot_state = load_boot_state(state_path=state_path)
                    runtime_state["boot_state"] = boot_state
                    runtime_state["stabilized"] = True
                    view.sync(board, boot_state, elapsed, True)
                    view.render(force=False)
                    logger.info("BOOT GUARD: Stabilized after {}ms; boot_strikes=0".format(elapsed))
                    logger.clear_breadcrumb("IDLE")
                    bp("[BOOT_GUARD] Stabilized after {}ms (boot_strikes=0)".format(elapsed))
                    break

                cur_s = elapsed // 1000
                if cur_s != last_draw_s:
                    last_draw_s = cur_s
                    view.sync(board, boot_state, elapsed, False)
                    view.render(force=False)
                    bp("[BOOT_GUARD] Stabilizing {}/5s (strike {}/{})...".format(
                        cur_s + 1,
                        boot_state.get("boot_strikes", 1),
                        boot_state.get("strike_limit", STRIKE_LIMIT),
                    ))
                _sleep_ms(100)
        else:
            runtime_state["stabilized"] = (boot_state.get("boot_strikes", 0) == 0)
            logger.clear_breadcrumb("IDLE")
            view.sync(board, boot_state, elapsed, runtime_state["stabilized"])
            view.render(force=False)

        gc.collect()
        free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        bp("<<PINHOS:BOOT_OK:v{}:FREE_RAM={}>>".format(
            manifest.get("version", "1.0.0-alpha.2"), free_b
        ))
        if interactive:
            ui_loop()
        return {
            "mode": "NORMAL",
            "ui_mode": ui.mode,
            "theme": theme_mgr.active.id,
            "version": manifest.get("version", "1.0.0-alpha.2"),
            "board": board.id,
            "stabilized": runtime_state["stabilized"],
            "strikes": boot_state.get("boot_strikes", 0),
            "free_sram": free_b,
        }

    except Exception as exc:
        err_msg = repr(exc)
        boot_state["last_error"] = err_msg[:120]
        save_boot_state(boot_state, state_path=state_path)
        if runtime_state.get("logger"):
            runtime_state["logger"].exception("BOOT", exc)
        if boot_state.get("boot_strikes", 0) >= int(boot_state.get("strike_limit", STRIKE_LIMIT)):
            return enter_safe_recovery_mode(
                board=runtime_state.get("board"),
                state=boot_state,
                reason=err_msg,
                state_path=state_path,
                interactive=interactive,
            )
        raise


if __name__ == "__main__":
    start(
        skip_strike_increment=bool(globals().get("_FLASH_GUARD_ACTIVE", False)),
        interactive=True,
    )

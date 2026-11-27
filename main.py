# PinhOS v1.0.0-alpha.5.0 — Phase 1+2+3.1+4.1 Boot Entry, 3-Strike Crash Guard, Desktop Home, Dual-UI & WebPortal IDE (main.py)
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
    "serial_link": False,
    "web_server": None,
    "web_active": False,
    "ntp_pending": False,
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
    """Reset boot strikes, persist RTC state if valid, and perform a clean soft reset."""
    recovery_reset_strikes(state_path=state_path)
    try:
        from core.config import save_rtc_state
        save_rtc_state(runtime_state.get("board"))
    except Exception:
        pass
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
        "ui": ui_loop,
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
        if hasattr(board, "init_uart_bridge"):
            try:
                board.init_uart_bridge(rebind=True)
            except Exception:
                pass
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

    if hasattr(board, "init_uart_bridge"):
        try:
            board.init_uart_bridge(rebind=True)
        except Exception:
            pass

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
    gc.collect()
    import ui._log_view as _lv
    try:
        return _lv.open_log_viewer(board, ui, logger, kind=kind)
    finally:
        _lv = None
        sys.modules.pop("ui._log_view", None)
        gc.collect()


_DESKTOP_HINTS = "F1:Help F2:Thm F3:Mode F4:Cfg F5:Notes"
_DASHBOARD_HINTS = "F1:Help F2:Thm F3:Mode F4:Cfg F5:Notes"
_SHIFT_HINTS = "F6:Web F7:LNK F8:Mouse F9:Edit F10:Test"


def confirm_dialog(board, ui, title, lines, footer="[Y/ENTER] Yes  [N/ESC] No", kind="warn"):
    from ui.widgets import confirm_dialog as _cd
    return _cd(board, ui, title, lines, footer=footer, kind=kind)


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


def _ensure_manifest():
    """Return runtime manifest, loading version.json lazily (e.g. ui_loop() relaunched without start())."""
    m = runtime_state.get("manifest")
    if not m:
        try:
            from core.config import load_version_manifest
            m = load_version_manifest()
        except Exception:
            m = {"version": "1.0.0-alpha.5.0", "arch": "armv7emsp"}
        runtime_state["manifest"] = m
    return m


def _sync_status_bar(status_bar, ui, board, manifest, chg_phase=0):
    bat = board.get_battery()
    ver = (manifest or {}).get("version", "1.0.0-alpha.5.0")
    cfg = runtime_state.get("config")
    wf_mode = str(cfg.get("wifi_indicator", "bars") if cfg else "bars").lower()
    wf_lvl, wf_txt = None, ""
    if wf_mode != "off":
        try:
            from net.wifi import get_wifi_bar_info
            wf_lvl, wf_txt = get_wifi_bar_info(wf_mode)
        except Exception:
            wf_lvl, wf_txt = None, ""
    bm = str(cfg.get("battery_indicator", "both") if cfg else "both").lower()
    bat_icon = (bat["percent"], bat["charging"], chg_phase if (bat["charging"] and bat["percent"] < 100) else 0) if bm in ("both", "icon") else None
    bat_txt = "{}%".format(bat["percent"]) if bm in ("both", "pct") else ""
    clk = board.get_timestamp_str(True)[:5]
    right_txt = " ".join([x for x in (wf_txt, clk, bat_txt) if x])

    status_bar.update(
        title="PinhOS v{}".format(ver),
        mode_label=ui.mode_badge,
        right_text=right_txt,
        wifi_level=wf_lvl,
        bat_info=bat_icon,
        serial_link=bool(runtime_state.get("serial_link", False)),
        web_active=bool(runtime_state.get("web_active", False)),
    )


class _DesktopView:
    """Phase 3.1 Android-Style Desktop Home Screen (Quick Strip + Split Telemetry/Notes Cards)."""

    def __init__(self, ui, manifest):
        from ui.widgets import StatusBar, FooterBar
        from ui.desktop import DesktopHome

        self.ui = ui
        self.screen = "desktop"
        self.manifest = manifest or {"version": "1.0.0-alpha.5.0", "arch": "armv7emsp"}
        self.status_bar = StatusBar(0, 0, 320, 20, title="PinhOS", mode_label=ui.mode_badge)
        self.desktop = DesktopHome(0, 22, 320, 252)
        self.footer_bar = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=_DESKTOP_HINTS)

        ui.clear_widgets()
        ui.add_widget(self.status_bar)
        ui.add_widget(self.desktop)
        ui.add_widget(self.footer_bar)
        ui.set_focus(self.desktop)

    def sync(self, board, boot_state, elapsed_ms, stabilized, status_msg="", status_kind="info", chg_phase=0, hints=None):
        _sync_status_bar(self.status_bar, self.ui, board, self.manifest, chg_phase=chg_phase)
        cfg = runtime_state.get("config")
        drawer_layout = str(cfg.get("launcher_layout", "grid") if cfg else "grid").upper()
        self.desktop.sync_telemetry(
            board,
            ui_mode=self.ui.mode_badge,
            drawer_layout=drawer_layout,
            stabilized=stabilized,
            web_active=bool(runtime_state.get("web_active", False)),
        )
        if not status_msg:
            status_msg = "Home | Theme: {} [{}]".format(self.ui.theme.name, self.ui.mode_badge)
            status_kind = "info"
        self.footer_bar.update(status=status_msg, status_kind=status_kind, hints=(hints if hints is not None else _DESKTOP_HINTS))

    def render(self, force=False):
        return self.ui.render(force=force)


class _DashboardView:
    """Phase 3.1 App Drawer: 3x2 GUI Mosaic / 1-6 TUI List + Dual RAM/CPU Sparkline Strip."""

    def __init__(self, ui, manifest, sel_action=0, layout="grid"):
        from ui.widgets import StatusBar, MosaicGrid, TelemetryStrip, FooterBar, DASHBOARD_ACTIONS

        self.ui = ui
        self.screen = "drawer"
        self.manifest = manifest or {"version": "1.0.0-alpha.5.0", "arch": "armv7emsp"}
        self.status_bar = StatusBar(0, 0, 320, 20, title="PinhOS", mode_label=ui.mode_badge)
        self.action_menu = MosaicGrid(
            4, 23, 312, 218,
            items=DASHBOARD_ACTIONS,
            selected=sel_action,
            cols=3,
            layout=layout,
        )
        self.telemetry_panel = TelemetryStrip(4, 245, 312, 28, max_samples=16)
        self.footer_bar = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=_DASHBOARD_HINTS)

        ui.clear_widgets()
        ui.add_widget(self.status_bar)
        ui.add_widget(self.action_menu)
        ui.add_widget(self.telemetry_panel)
        ui.add_widget(self.footer_bar)
        ui.set_focus(self.action_menu)

    def sync(self, board, boot_state, elapsed_ms, stabilized, status_msg="", status_kind="info", chg_phase=0, hints=None):
        free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        theme_name = self.ui.theme.name
        cfg = runtime_state.get("config")
        _sync_status_bar(self.status_bar, self.ui, board, self.manifest, chg_phase=chg_phase)
        try:
            import machine
            cpu_mhz = machine.freq() // 1000000
        except Exception:
            cpu_mhz = int(cfg.get("cpu_freq_mhz", 150) if cfg else 150)
        self.telemetry_panel.push(free_kb, cpu_mhz, board.get_cpu_temp_c(), ok=stabilized)
        if not status_msg:
            status_msg = "App Drawer | {} [{}]".format(theme_name, self.ui.mode_badge)
            status_kind = "info"
        self.footer_bar.update(status=status_msg, status_kind=status_kind, hints=(hints if hints is not None else _DASHBOARD_HINTS))

    def render(self, force=False):
        return self.ui.render(force=force)


def _prompt_quick_note(board, ui, fb):
    """Inline Quick Note entry on FooterBar (ENTER saves, ESC cancels)."""
    buf = ""
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while True:
        fb.update(
            status="NOTE: {}_".format(buf[-36:]),
            status_kind="info",
            hints="ENT:Save Note  BKSP:Del  ESC:Cancel",
        )
        ui.render(force=False)
        k = poll_fn() if poll_fn else None
        if k:
            ku = str(k).upper()
            if ku in ("ENTER", "RETURN"):
                board.beep(1400, 12)
                return buf.strip()
            if ku in ("ESC", "BACK"):
                board.beep(900, 10)
                return None
            if ku == "BACKSPACE":
                buf = buf[:-1]
            elif ku == "SPACE":
                if len(buf) < 80:
                    buf += " "
            elif len(k) == 1 and " " <= k <= "~":
                if len(buf) < 80:
                    buf += k
        _sleep_ms(25)


def open_menu_tree(board, ui, theme_mgr, cfg, logger, sandbox, manifest, root_cat, run_tool_cb):
    gc.collect()
    import ui.menu as _um
    try:
        return _um.open_menu_tree(board, ui, theme_mgr, cfg, logger, sandbox, manifest, root_cat, run_tool_cb)
    finally:
        _um = None
        for _m in ("ui.menu", "ui._menu_net", "ui._log_view", "net.sync"):
            sys.modules.pop(_m, None)
        gc.collect()


_REPL_KEEPALIVE = None


def _start_repl_keepalive():
    """After a deliberate serial Ctrl+C (dev/REPL mode), pause soft prompts while keeping Stage 2 HW WDT fed."""
    global _REPL_KEEPALIVE
    w = _WDT_OBJ or runtime_state.get("_wdt")
    if w is None:
        return
    if hasattr(w, "pause"):
        w.pause()
        bp("[WDT] Soft WDT paused for REPL (Stage 1 timer keeps HW WDT fed)")
        return
    if _REPL_KEEPALIVE is not None:
        return
    try:
        import machine
        _REPL_KEEPALIVE = machine.Timer(-1, period=2000, mode=machine.Timer.PERIODIC, callback=lambda t: w.feed())
        bp("[WDT] REPL keep-alive timer active")
    except Exception as e:
        bp("[WDT_ERR] keepalive", repr(e))


def _stop_repl_watcher():
    global _REPL_KEEPALIVE
    w = _WDT_OBJ or runtime_state.get("_wdt")
    if w is not None and hasattr(w, "resume"):
        w.resume()
    if _REPL_KEEPALIVE is not None:
        try:
            _REPL_KEEPALIVE.deinit()
        except Exception:
            pass
        _REPL_KEEPALIVE = None
    if builtins is not None:
        t = getattr(builtins, "_pinhos_repl_timer", None)
        if t is not None:
            try:
                t.deinit()
            except Exception:
                pass
            try:
                setattr(builtins, "_pinhos_repl_timer", None)
            except Exception:
                pass


def toggle_serial_link(board=None, logger=None, enable=None):
    """
    COM4 Serial Link (LNK) gate & toggle:
    - When ON: attaches UART0 @ 115200 to os.dupterm(0), accepts COM4 Ctrl+C/REPL, shows LNK badge, suppresses sleep.
    - When OFF: detaches os.dupterm(None, 0) and ignores COM4 RX until explicitly re-enabled.
    Returns (active_bool, status_msg).
    """
    if board is None:
        board = runtime_state.get("board")
    if logger is None:
        logger = runtime_state.get("logger")
    cur = bool(runtime_state.get("serial_link", False))
    nxt = (not cur) if enable is None else bool(enable)
    runtime_state["serial_link"] = nxt
    msg = "COM4 Serial Link: LNK ON (sleep off)" if nxt else "COM4 Serial Link: OFF (locked)"
    if board is not None:
        if nxt:
            if hasattr(board, "set_serial_link"):
                board.set_serial_link(True)
            elif hasattr(board, "init_uart_bridge"):
                board.init_uart_bridge(rebind=True)
            bp("[SERIAL_LINK]", msg)
        else:
            bp("[SERIAL_LINK]", msg)
            if hasattr(board, "set_serial_link"):
                board.set_serial_link(False)
        board.beep(1400 if nxt else 950, 12)
    else:
        bp("[SERIAL_LINK]", msg)
    if logger is not None:
        try:
            logger.info("SERIAL_LINK: " + ("ON" if nxt else "OFF"))
        except Exception:
            pass
    return nxt, msg


def show_serial_link_dialog(board, ui):
    """Show confirmation Dialog popup when COM4 Serial Link (LNK) is enabled."""
    if board is None or ui is None:
        return
    from ui.widgets import Dialog
    dlg = Dialog(
        14, 76, 292, 152,
        title="COM4 SERIAL LINK ACTIVE",
        lines=[
            "Port  : UART0 115200 8N1 (COM4)",
            "REPL  : Host sync & Ctrl+C open",
            "Sleep : Suppressed while LNK ON",
            "Lock again: [Shift+F7 / CTRL+Q]",
        ],
        footer="[ENT / ESC] Continue",
        kind="ok",
    )
    ui.add_widget(dlg)
    ui.render(force=True)
    board.clear_input()
    pf = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            feed_wdt()
            k = pf() if pf else None
            if k and str(k).upper() in ("ENTER", "RETURN", "ESC", "SPACE", " ", "Q", "BACK", "BACKSPACE"):
                board.beep(1100, 10)
                break
            if runtime_state.get("web_active"):
                step_webportal(20)
            else:
                _sleep_ms(30)
    except KeyboardInterrupt:
        ui.remove_widget(dlg)
        ui.mark_all_dirty(True)
        raise
    ui.remove_widget(dlg)
    ui.mark_all_dirty(True)
    board.clear_input()


def start_webportal(board=None, cfg=None, logger=None, host="0.0.0.0", port=None):
    from web import start_portal
    ok, msg = start_portal(runtime_state, board=board, cfg=cfg, logger=logger, host=host, port=port)
    bp("[WEBPORTAL]", msg)
    return ok, msg


def stop_webportal(logger=None):
    if runtime_state.get("web_server") is None and not runtime_state.get("web_active"):
        return True, "WebPortal IDE stopped"
    from web import stop_portal
    return stop_portal(runtime_state)


def toggle_webportal(board=None, cfg=None, logger=None):
    from web import toggle_portal
    ok, msg = toggle_portal(runtime_state, board=board, cfg=cfg, logger=logger)
    bp("[WEBPORTAL]", msg)
    return ok, msg


_WDT_OBJ = None


def feed_wdt():
    """Feed RP2350 hardware watchdog if enabled."""
    w = _WDT_OBJ or runtime_state.get("_wdt")
    if w is None and builtins is not None:
        w = getattr(builtins, "_pinhos_wdt", None)
    if w is not None:
        try:
            w.feed()
        except Exception:
            pass


def enable_wdt(timeout_ms=8000, soft_timeout_s=30):
    """Enable Two-Stage Soft (15/30/60s/OFF) + Hard (8s RP2350) Watchdog once after boot stabilization (#54)."""
    global _WDT_OBJ
    ms = int(timeout_ms or 0)
    if ms <= 0:
        return False
    ms = min(8388, max(1000, ms))
    soft_s = max(0, int(soft_timeout_s or 0))
    try:
        existing = _WDT_OBJ or runtime_state.get("_wdt")
        if existing is None and builtins is not None:
            existing = getattr(builtins, "_pinhos_wdt", None)
        if existing is not None:
            if hasattr(existing, "attach"):
                existing.attach(
                    board=runtime_state.get("board"),
                    ui=runtime_state.get("ui"),
                    logger=runtime_state.get("logger"),
                )
            if hasattr(existing, "set_soft_timeout_s"):
                existing.set_soft_timeout_s(soft_s)
            if hasattr(existing, "resume"):
                existing.resume()
            existing.feed()
            return True
        from core.watchdog import TwoStageWatchdog
        w = TwoStageWatchdog(
            hw_timeout_ms=ms,
            soft_timeout_s=soft_s,
            board=runtime_state.get("board"),
            ui=runtime_state.get("ui"),
            logger=runtime_state.get("logger"),
            arm_hw=True,
        )
        _WDT_OBJ = w
        runtime_state["_wdt"] = w
        sys.modules["__pinhos_wdt__"] = w  # shared handle (builtins is read-only on RP2350)
        if builtins is not None:
            try:
                setattr(builtins, "_pinhos_wdt", w)
            except Exception:
                pass
        _tmode = "timer" if getattr(w, "_timer", None) is not None else "coop"
        bp("[WDT] Enabled Two-Stage Watchdog (soft={}s, hw={}ms, {})".format(soft_s, ms, _tmode))
        lg = runtime_state.get("logger")
        if lg is not None:
            try:
                if hasattr(lg, "log_wdt"):
                    lg.log_wdt("ARMED (soft={}s hw={}ms {})".format(soft_s, ms, _tmode))
                else:
                    lg.info("WDT: Armed (soft={}s hw={}ms {})".format(soft_s, ms, _tmode))
            except Exception:
                pass
        return True
    except Exception as e:
        bp("[WDT_ERR]", repr(e))
    return False


def step_webportal(slice_ms=15):
    feed_wdt()
    ws = runtime_state.get("web_server")
    if ws is not None and ws.running:
        try:
            ws.step(slice_ms)
            return True
        except Exception as e:
            bp("[WEBPORTAL_STEP_ERR]", repr(e))
    return False


def _enter_sleep_mode(board, ui, logger, countdown_s=5):
    """
    Android-style Sleep Mode with 5-second countdown Dialog:
    - Suppressed whenever COM4 Serial Link (LNK) or WebPortal (WEB) is active.
    - Any key during the 5s countdown cancels sleep immediately.
    - After countdown, dims LCD & KB backlights to 0% (Core 1 & COM4 stay intact).
    - Any key / Power button tap wakes instantaneously and restores backlights.
    Returns True if slept & woke, False if cancelled or suppressed.
    """
    if runtime_state.get("serial_link") or runtime_state.get("web_active"):
        bp("[POWER] Sleep suppressed while LNK or WebPortal is active.")
        return False
    from ui.widgets import Dialog
    dlg = Dialog(
        20, 82, 280, 144,
        title="SLEEP MODE",
        lines=[
            "Entering low-power sleep in {}s...".format(countdown_s),
            "Display & keyboard backlight",
            "will turn off to save battery.",
            "",
        ],
        footer="[ANY KEY] Cancel Sleep",
        kind="warn",
    )
    ui.add_widget(dlg)
    ui.render(force=False)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

    # 5-second live countdown (any key cancels)
    for rem in range(int(countdown_s), 0, -1):
        dlg.set_content(lines=[
            "Entering low-power sleep in {}s...".format(rem),
            "Display & keyboard backlight",
            "will turn off to save battery.",
            "",
        ])
        ui.render(force=False)
        t0 = _ticks_ms()
        while _ticks_diff(_ticks_ms(), t0) < 1000:
            if poll_fn and poll_fn() is not None:
                board.beep(1200, 10)
                ui.remove_widget(dlg)
                ui.mark_all_dirty(True)
                board.clear_input()
                return False
            _sleep_ms(30)

    # Enter low-power standby (persist RTC first, zero backlight, low poll cadence, Core 1 & COM4 preserved)
    ui.remove_widget(dlg)
    ui.mark_all_dirty(True)
    try:
        from core.config import save_rtc_state
        save_rtc_state(board)
    except Exception:
        pass
    orig_lcd = board.get_backlight()
    orig_kb = board.get_kb_backlight()
    if logger:
        try:
            logger.info("POWER: Entering sleep standby")
        except Exception:
            pass
    board.set_backlight(0)
    board.set_kb_backlight(0)
    board.clear_input()
    gc.collect()

    wdt_ref = _WDT_OBJ or runtime_state.get("_wdt")
    if wdt_ref is not None and hasattr(wdt_ref, "pause"):
        wdt_ref.pause()
    try:
        ticks = 0
        while True:
            feed_wdt()
            if poll_fn and poll_fn() is not None:
                break
            ticks += 1
            if ticks >= 50:
                ticks = 0
                gc.collect()
            _sleep_ms(120)
    finally:
        if wdt_ref is not None and hasattr(wdt_ref, "resume"):
            wdt_ref.resume()
        board.set_backlight(max(20, orig_lcd))
        board.set_kb_backlight(orig_kb)
        board.clear_input()
        board.beep(1400, 12)
        if logger:
            try:
                logger.info("POWER: Woke from sleep")
            except Exception:
                pass
    return True


def _repl_standby_popup(board, ui, logger):
    """Non-blocking wrapper for backward compatibility: toggles COM4 Serial Link (LNK) without blocking UI."""
    toggle_serial_link(board, logger)
    return False


def _init_interactive_services(board, cfg, logger):
    """
    Idempotent interactive-session startup hooks (#29):
    Runs once when entering ui_loop(), so BOTH cold boots (start(interactive=True))
    AND deploy boots (picocalc.ps1: start(interactive=False) -> ui_loop()) queue
    non-blocking Wi-Fi auto-connect and honor webportal_autostart=True.
    Hardware WDT is armed only on standalone boots (_standalone_boot=True) so
    COM4 upload/test Raw REPL sessions are never reset mid-command.
    """
    if runtime_state.get("_interactive_init_done"):
        return False
    runtime_state["_interactive_init_done"] = True
    runtime_state["wifi_bg_pending"] = True
    if runtime_state.get("_standalone_boot") and runtime_state.get("stabilized") and not runtime_state.get("serial_link"):
        try:
            enable_wdt(
                int(cfg.get("wdt_timeout_ms", 8000)) if cfg else 8000,
                soft_timeout_s=int(cfg.get("soft_wdt_s", 30)) if cfg else 30,
            )
        except Exception:
            pass
    if cfg and cfg.get("webportal_autostart", False) and not runtime_state.get("web_active"):
        start_webportal(board=board, cfg=cfg, logger=logger)
    return True


def ui_loop(sel_action=0):
    """
    Interactive Phase 2 Dual-UI keyboard event loop.
    Polls STM32 I2C keyboard via board.poll_key() without starving Core 1 LCD refresh,
    supports live GUI<->TUI switching ([TAB]/[M]) and theme cycling ([T]),
    and cleanly exits to REPL on [ALT+Q] (bare [Q] asks for confirmation) or serial Ctrl+C (\\x03).
    """
    _stop_repl_watcher()
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
    if cfg is None:
        try:
            from core.config import ConfigManager
            cfg = ConfigManager()
            runtime_state["config"] = cfg
        except Exception:
            cfg = None
    logger = runtime_state.get("logger")
    if logger is None:
        try:
            from core.logger import get_logger
            logger = get_logger()
            runtime_state["logger"] = logger
        except Exception:
            logger = None
    if runtime_state.get("swap") is None:
        try:
            from core.swap import get_swap_manager
            runtime_state["swap"] = get_swap_manager()
        except Exception:
            pass
    _init_interactive_services(board, cfg, logger)
    theme_mgr, ui = _ensure_ui_services(board, cfg=cfg)
    manifest = _ensure_manifest()
    boot_state = runtime_state.get("boot_state") or load_boot_state()
    sandbox = runtime_state.get("sandbox")
    from boards.base import MOD_ALT, MOD_CTRL, MOD_SHIFT

    def _cur_layout():
        return str(cfg.get("launcher_layout", "grid") if cfg else "grid").lower()

    screen = str(cfg.get("boot_screen", "desktop") if cfg else "desktop").lower()
    if screen not in ("desktop", "drawer"):
        screen = "desktop"
    drawer_sel = sel_action

    def _mount_view(scr=None):
        nonlocal screen
        if scr is not None:
            screen = scr
        if screen == "desktop":
            return _DesktopView(ui, manifest)
        return _DashboardView(ui, manifest, sel_action=drawer_sel, layout=_cur_layout())

    view = _mount_view(screen)
    prev_crash = runtime_state.get("prev_crash")
    if prev_crash:
        status_msg = "Prev Crash ({})! Press [^L] Logs".format(prev_crash.get("op", "?"))
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

    def _exec_sandbox_file(path, label, wait_after=False, args=None):
        poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
        _drain_keys(100)
        if logger:
            logger.set_breadcrumb("TOOL", label[:30])
        smsg, skind = label + " done", "ok"
        gc.collect()
        sbx = sandbox
        loaded_sbx = False
        if sbx is None:
            from core.sandbox import SandboxRunner
            sbx = SandboxRunner(board=board, config=cfg, swap=runtime_state.get("swap"), logger=logger, theme=theme_mgr, ui=ui)
            loaded_sbx = True
        res_dict = None
        smsg, skind = label[:16] + " ERR", "err"
        try:
            from core.sandbox import SandboxError
            try:
                res = sbx.run_file(path, args=args, wait_on_error=True)
                res_dict = res
                if res.get("aborted"):
                    smsg = "Force-closed {}".format(label[:18])
                    skind = "warn"
                else:
                    smsg = "{} OK (d={}B)".format(label[:16], res.get("sram_delta", 0))
                    skind = "ok" if res.get("ok") else "err"
                if logger:
                    blk = 0
                    try:
                        from core.memutil import largest_free
                        blk = largest_free(cap=98304)
                    except Exception:
                        pass
                    logger.info("TOOL {}: ok={} delta={}B blk={}B".format(label, res.get("ok"), res.get("sram_delta", 0), blk))
                    if not runtime_state.get("_heap_first_tool_logged"):
                        runtime_state["_heap_first_tool_logged"] = True
                        _log_heap_stage(logger, "FIRST_TOOL:" + str(label)[:14])
                if wait_after and res.get("ok"):
                    board.clear_input()
                    while True:
                        feed_wdt()
                        if poll_fn and poll_fn() is not None:
                            board.beep(1100, 10)
                            break
                        _sleep_ms(30)
            except SandboxError as se:
                smsg = str(se)[:44]
                skind = "err"
                res_dict = {"ok": False, "error": str(se), "sram_before": gc.mem_free() if hasattr(gc, "mem_free") else 0, "sram_after": gc.mem_free() if hasattr(gc, "mem_free") else 0}
                if logger:
                    try:
                        if hasattr(logger, "crash_note"):
                            logger.crash_note("SANDBOX({})".format(label[:20]), str(se))
                        else:
                            logger.warn("TOOL {} BLOCKED: {}".format(label, str(se)[:80]))
                    except Exception:
                        pass
        finally:
            if loaded_sbx:
                sbx = None
                sys.modules.pop("core.sandbox", None)
                gc.collect()
            if logger:
                try:
                    logger.clear_breadcrumb("IDLE")
                except Exception:
                    pass
        runtime_state["_last_run_res"] = res_dict
        _drain_keys(120)
        theme_mgr._push_to_board(theme_mgr.active)
        return smsg, skind

    def _toggle_webportal_ui():
        nonlocal status_msg, status_kind
        gc.collect(); gc.collect()
        active, wmsg = toggle_webportal(board=board, cfg=cfg, logger=logger)
        status_msg = ("WebPortal: " + str(wmsg)) if active else str(wmsg)
        status_kind = "ok" if active else "info"
        if active:
            _ws = runtime_state.get("web_server")
            _tok = str(getattr(_ws, "token", "")) if _ws is not None else ""
            try:
                from web import portal_url
                _url = portal_url(getattr(_ws, "port", 8080))
            except Exception:
                _url = "http://0.0.0.0:8080"
            from ui.widgets import Dialog
            _dlg = Dialog(
                12, 76, 296, 152,
                title="WEBPORTAL IDE ACTIVE",
                lines=[
                    "URL:",
                    " " + str(_url)[:34],
                    "Token (X-PinhOS-Token):",
                    " " + _tok,
                    "Toggle anytime: [Shift+F6]",
                ],
                footer="[ENT / ESC] Continue",
                kind="ok",
            )
            ui.add_widget(_dlg)
            ui.render(force=True)
            board.clear_input()
            _pf = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
            while True:
                feed_wdt()
                _k = _pf() if _pf else None
                if _k and str(_k).upper() in ("ENTER", "ESC", "SPACE", " ", "Q", "BACKSPACE"):
                    board.beep(1100, 10)
                    break
                step_webportal(20)
            ui.remove_widget(_dlg)
            _dlg = None
            gc.collect()
        return active

    def _run_action(act_id):
        nonlocal status_msg, status_kind, view, drawer_sel, theme_mgr, ui
        if act_id != "refresh":
            from core.memutil import ensure_heap
            _pf_free, _pf_ok = ensure_heap(runtime_state)
            if not _pf_ok and logger:
                logger.warn("MEMGUARD: low heap before {} (free={}B)".format(act_id, _pf_free))
        if screen == "drawer" and hasattr(view, "action_menu"):
            drawer_sel = view.action_menu.selected

        if act_id.startswith("cat:"):
            board.beep(1300, 12)
            _drain_keys(100)
            res = open_menu_tree(
                board, ui, theme_mgr, cfg, logger, sandbox, manifest,
                act_id[4:], _exec_sandbox_file,
            )
            _drain_keys(100)
            if res == "EXIT_REPL":
                return "EXIT_REPL"
            if res == "SLEEP_NOW":
                return "SLEEP_NOW"
            if res == "RUN_SELFTEST":
                return _run_action("selftest")
            if res == "TOGGLE_WEBPORTAL":
                # ui.menu has already been purged & GC'd -> ~35 KB extra contiguous SRAM for uasyncio + lwIP!
                _toggle_webportal_ui()
            elif isinstance(res, tuple) and len(res) >= 4 and res[0] == "RUN_SANDBOX":
                # ui.menu has already been purged & GC'd -> ~35 KB extra contiguous SRAM for apps/tools!
                from core.memutil import ensure_heap
                ensure_heap(runtime_state, min_free=98304, min_blk=32768)
                status_msg, status_kind = _exec_sandbox_file(res[1], res[2], res[3])
            theme_mgr._push_to_board(theme_mgr.active)
            view = _mount_view()
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)
            return None

        if act_id.startswith("tool:"):
            act_id = act_id[5:]

        from ui.widgets import TOOL_MAP
        if act_id in TOOL_MAP:
            path, label, wait_after = TOOL_MAP[act_id]
            board.beep(1400, 15)
            status_msg, status_kind = _exec_sandbox_file(path, label, wait_after)
            view = _mount_view()
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "selftest":
            board.beep(1400, 15)
            _drain_keys(120)
            if logger:
                logger.set_breadcrumb("SELFTEST", "run_all")
            _saved_rs = dict(runtime_state)
            _this_mod = sys.modules.get(__name__) or sys.modules.get("main") or sys.modules.get("_pinhos_main")
            view = None
            if ui is not None:
                ui.deinit()
            ui = None
            theme_mgr = None
            runtime_state["ui"] = None
            runtime_state["theme"] = None
            gc.collect()
            import tests.selftest as _st
            try:
                res = _st.run_all(interactive_wait=True)
            finally:
                _st = None
                for _tm in ("tests.selftest", "tests.selftest_p3", "tests.selftest_p4", "tests.selftest_stress", "tests", "boards.generic_spi"):
                    sys.modules.pop(_tm, None)
                runtime_state.update(_saved_rs)
                runtime_state["ui"] = None
                runtime_state["theme"] = None
                if _this_mod is not None:
                    sys.modules["main"] = _this_mod
                _saved_rs = None
                gc.collect()
                gc.collect()
                theme_mgr, ui = _ensure_ui_services(board, cfg=cfg)
                if _WDT_OBJ is not None and hasattr(_WDT_OBJ, "attach"):
                    _WDT_OBJ.attach(board=board, ui=ui, logger=logger)
            if logger:
                logger.info("SELFTEST: {}/{} {}".format(
                    res.get("passed", 0), res.get("total", 12), "PASS" if res.get("ok") else "FAIL"
                ))
                logger.clear_breadcrumb("IDLE")
            _drain_keys(150)
            theme_mgr._push_to_board(theme_mgr.active)
            view = _mount_view()
            status_msg = "Self-Test {}/{} {}".format(
                res.get("passed", 0), res.get("total", 12), "PASS" if res.get("ok") else "FAIL"
            )
            status_kind = "ok" if res.get("ok") else "err"
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "logs":
            board.beep(1400, 12)
            _drain_keys(100)
            prev_c = runtime_state.get("prev_crash")
            lkind = "wdt" if (prev_c and prev_c.get("wdt_reset")) else ("crash" if prev_c else "system")
            open_log_viewer(board, ui, logger, kind=lkind)
            runtime_state["prev_crash"] = None
            _drain_keys(120)
            view = _mount_view()
            status_msg = "Returned from Logs"
            status_kind = "info"
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

        elif act_id == "refresh":
            board.beep(1600, 15)
            gc.collect()
            if board.get_backlight() < 40:
                board.set_backlight(80)
            theme_mgr._push_to_board(theme_mgr.active)
            if screen == "desktop" and hasattr(view, "desktop"):
                view.desktop.reload_notes()
            status_msg = "Display & Telemetry OK @ " + board.get_timestamp_str(True)
            status_kind = "ok"
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)

    def _finish_menu_res(res):
        nonlocal status_msg, status_kind, view, last_act_ms
        if res == "EXIT_REPL":
            on, smsg = toggle_serial_link(board, logger)
            status_msg, status_kind = smsg, ("ok" if on else "info")
            view = _mount_view()
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)
        elif res == "SLEEP_NOW":
            if runtime_state.get("serial_link") or runtime_state.get("web_active"):
                status_msg, status_kind = "Sleep disabled while LNK/WEB is ON", "warn"
            else:
                try:
                    from core.config import save_rtc_state
                    save_rtc_state(board)
                except Exception:
                    pass
                slept = _enter_sleep_mode(board, ui, logger, countdown_s=5)
                status_msg, status_kind = ("Woke from Sleep" if slept else "Sleep Cancelled"), "ok"
            view = _mount_view()
            view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
            view.render(force=True)
        last_act_ms = _ticks_ms()

    board.clear_input()
    theme_mgr._push_to_board(theme_mgr.active)
    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
    view.render(force=True)
    if not runtime_state.get("_heap_idle_logged"):
        runtime_state["_heap_idle_logged"] = True
        _log_heap_stage(logger, "IDLE_DESKTOP")
    # Enforce COM4 Serial Link lock state on UI entry (default OFF -> press Shift+F7 / CTRL+Q to open)
    if hasattr(board, "set_serial_link"):
        board.set_serial_link(bool(runtime_state.get("serial_link", False)))

    idle_ticks = 0
    anim_ticks = 0
    mg_level = 0
    chg_phase = 0
    last_shift_bar = False
    last_act_ms = _ticks_ms()
    last_rtc_save_ms = _ticks_ms()
    last_ntp_sync_ms = _ticks_ms()
    ntp_retry_at_ms = 0
    ntp_retries = 0
    try:
        while True:
            poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
            key = poll_fn() if poll_fn else None
            # Live SHIFT keybar toggle (F1-F5 <-> F6-F10) using partial FooterBar-only redraw
            _sh_now = bool(board.get_modifiers() & MOD_SHIFT)
            if _sh_now != last_shift_bar:
                last_shift_bar = _sh_now
                view.footer_bar.update(hints=_SHIFT_HINTS if _sh_now else _DESKTOP_HINTS)
                view.render(force=False)
            if key:
                idle_ticks = 0
                last_act_ms = _ticks_ms()
                k = str(key).upper()
                mods = board.get_modifiers()
                ctrl = bool(mods & MOD_CTRL)
                shift = bool(mods & MOD_SHIFT)
                alt = bool(mods & MOD_ALT)

                if (ctrl and k == "P") or getattr(board, "pending_screenshot", None):
                    gc.collect()
                    from ui.widgets import show_screenshot_toast
                    _, smsg = show_screenshot_toast(board, ui, view.footer_bar)
                    if smsg:
                        status_msg = smsg
                        status_kind = "ok"
                        view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                        view.render(force=True)
                    continue

                if k == "POWER" or (ctrl and k == "Z"):
                    board.beep(900, 12)
                    if runtime_state.get("serial_link") or runtime_state.get("web_active"):
                        status_msg = "Sleep disabled while LNK/WEB is ON"
                        status_kind = "warn"
                    else:
                        try:
                            from core.config import save_rtc_state
                            save_rtc_state(board)
                        except Exception:
                            pass
                        slept = _enter_sleep_mode(board, ui, logger, countdown_s=5)
                        status_msg = "Woke from Sleep" if slept else "Sleep Cancelled"
                        status_kind = "ok"
                    last_act_ms = _ticks_ms()
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
                    view.render(force=True)

                elif (ctrl and k == "Q") or (shift and k == "F7"):
                    # COM4 Serial Link (LNK) toggle: gates UART0 dupterm/Ctrl+C & shows popup when ON
                    on, smsg = toggle_serial_link(board, logger)
                    last_act_ms = _ticks_ms()
                    status_msg = smsg
                    status_kind = "ok" if on else "info"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=False)
                    if on:
                        show_serial_link_dialog(board, ui)
                        view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                        view.render(force=True)
                    continue

                elif shift and k == "F6":
                    board.beep(1350, 12)
                    _toggle_webportal_ui()
                    theme_mgr._push_to_board(theme_mgr.active)
                    view = _mount_view()
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)
                    last_act_ms = _ticks_ms()

                elif shift and k == "F8":
                    board.beep(1250, 10)
                    status_msg = "Mouse mode: Phase 6"
                    status_kind = "info"
                    from ui.widgets import show_toast_dialog
                    show_toast_dialog(
                        board, ui,
                        title="POINTER / MOUSE",
                        lines=[
                            "Mouse mode: Phase 6",
                            "BLE HID mouse & trackball",
                            "arrives in Phase 6 (net/ble.py).",
                        ],
                        fb=view.footer_bar,
                        status_msg=status_msg,
                        kind="info",
                        timeout_ticks=25,
                    )
                    last_act_ms = _ticks_ms()
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)

                elif (shift and k == "F9") or (screen == "desktop" and k == "E" and not ctrl):
                    from ui.desktop import NOTES_PATH
                    from core.config import PINHOS_ROOT
                    board.beep(1400, 12)
                    cur_scr = screen
                    status_msg, status_kind = _exec_sandbox_file(
                        PINHOS_ROOT + "/tools/editor.py", "Notes Editor", False, args={"path": NOTES_PATH}
                    )
                    view = _mount_view(cur_scr)
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)
                    last_act_ms = _ticks_ms()

                elif shift and k == "F10":
                    _run_action("selftest")

                elif k == "F1" and not (ctrl or alt or shift):
                    board.beep(1300, 10)
                    from ui.desktop import show_help_dialog
                    show_help_dialog(board, ui)
                    last_act_ms = _ticks_ms()
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)

                elif (k == "F2" and not (ctrl or alt or shift)) or (ctrl and k == "T"):
                    from core.memutil import ensure_heap
                    ensure_heap(runtime_state, min_free=65536, min_blk=16384)
                    new_theme = ui.cycle_theme(step=1, persist=True)
                    if logger:
                        logger.info("UI: Theme -> {}".format(new_theme.id))
                    board.beep(1500, 12)
                    status_msg = "Theme: {} [{}]".format(new_theme.name, ui.mode_badge)
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)

                elif (k == "F3" and not (ctrl or alt or shift)) or k == "TAB" or (ctrl and k == "M"):
                    ui.toggle_mode(persist=True)
                    if logger:
                        logger.info("UI: Mode -> {}".format(ui.mode_badge))
                    board.beep(1300, 12)
                    status_msg = "Switched to {} Mode ({})".format(ui.mode_badge, ui.theme.name)
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)

                elif k == "F4" and not (ctrl or alt or shift):
                    _finish_menu_res(_run_action("cat:settings"))

                elif k == "F5" and alt:
                    # ALT+F5 once = Hard Reload UI; ALT+F5 twice within 3s = hardware reset escape hatch
                    now_ms = _ticks_ms()
                    if last_reload_ms and _ticks_diff(now_ms, last_reload_ms) < 3000:
                        try:
                            from core.config import save_rtc_state
                            save_rtc_state(board)
                        except Exception:
                            pass
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
                    if hasattr(board, "init_uart_bridge"):
                        try:
                            board.init_uart_bridge(rebind=True)
                        except Exception:
                            pass
                    if hasattr(board, "reset_default_lut"):
                        board.reset_default_lut()
                    if board.get_backlight() < 50:
                        board.set_backlight(80)
                    theme_mgr.apply(theme_mgr.active.id, persist=False, notify=False)
                    ui.set_mode(ui.mode, persist=False)
                    view = _mount_view()
                    gc.collect()
                    board.beep(1200, 12)
                    board.beep(1600, 15)
                    status_msg = "Reload OK [ALT+F5x2=Reboot]"
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
                    view.render(force=True)

                elif (k == "F5" and not (ctrl or alt or shift)) or (screen == "desktop" and k == "N" and not ctrl):
                    board.beep(1300, 10)
                    txt = _prompt_quick_note(board, ui, view.footer_bar)
                    if txt:
                        if screen == "desktop" and hasattr(view, "desktop"):
                            saved_n = view.desktop.add_note(txt)
                        else:
                            from ui.desktop import append_note
                            saved_n = append_note(txt)
                        if saved_n:
                            status_msg, status_kind = "Note saved to notes.txt", "ok"
                        else:
                            status_msg, status_kind = "Failed to save note", "err"
                    else:
                        status_msg, status_kind = "Note cancelled", "info"
                    last_act_ms = _ticks_ms()
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)

                elif ctrl and k == "B":
                    _run_action("shell")

                elif ctrl and k == "F":
                    _run_action("files")

                elif ctrl and k == "S":
                    _run_action("sysmon")

                elif ctrl and k == "E":
                    _run_action("editor")

                elif ctrl and k == "U":
                    _run_action("uart")

                elif ctrl and k == "N":
                    _run_action("net")

                elif ctrl and k == "V":
                    cur_l = _cur_layout()
                    nxt = "list" if cur_l == "grid" else "grid"
                    if cfg:
                        cfg.set("launcher_layout", nxt, save_now=True)
                    if screen == "drawer" and hasattr(view, "action_menu"):
                        view.action_menu.set_layout(nxt)
                    board.beep(1350, 12)
                    status_msg = "Drawer Layout: {} [{}]".format(nxt.upper(), ui.mode_badge)
                    status_kind = "ok"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind)
                    view.render(force=True)

                elif ctrl and k == "L":
                    _run_action("logs")

                elif ctrl and k == "R":
                    _run_action("refresh")

                elif screen == "desktop" and k in ("LEFT", "RIGHT", "UP"):
                    if ui.handle_key(k, allow_hotkeys=False):
                        board.beep(1100, 8)
                        view.render(force=False)

                elif screen == "desktop" and k == "DOWN":
                    if view.desktop.strip_sel is not None:
                        view.desktop.set_strip_sel(None)
                        board.beep(1050, 8)
                        view.render(force=False)
                    else:
                        board.beep(1350, 12)
                        view = _mount_view("drawer")
                        status_msg = "App Drawer [ESC:Home]"
                        status_kind = "info"
                        view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                        view.render(force=True)

                elif screen == "drawer" and k in ("UP", "DOWN", "LEFT", "RIGHT"):
                    if ui.handle_key(k, allow_hotkeys=False):
                        drawer_sel = view.action_menu.selected
                        board.beep(1100, 8)
                        # Partial dirty-row redraw ONLY (zero full-screen clear!)
                        view.render(force=False)

                elif k == "HOME":
                    board.beep(1350, 12)
                    target = "drawer" if screen == "desktop" else "desktop"
                    view = _mount_view(target)
                    status_msg = "App Drawer [ESC:Home]" if target == "drawer" else "Desktop Home"
                    status_kind = "info"
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=True)

                elif screen == "desktop" and k in ("ENTER", "SPACE", " "):
                    sel_act = view.desktop.get_selected_action()
                    if sel_act:
                        drawer_sel = view.desktop.strip_sel or 0
                        _finish_menu_res(_run_action(sel_act))
                    else:
                        board.beep(1350, 12)
                        view = _mount_view("drawer")
                        status_msg = "App Drawer [ESC:Home]"
                        status_kind = "info"
                        view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                        view.render(force=True)

                elif screen == "drawer" and k in ("ENTER", "SPACE", " "):
                    item = view.action_menu.get_selected_item()
                    if isinstance(item, dict) and item.get("id"):
                        _finish_menu_res(_run_action(item["id"]))

                elif k in ("1", "2", "3", "4", "5", "6"):
                    _CAT_IDS = ("cat:toolkit", "cat:files", "cat:apps", "cat:system", "cat:settings", "cat:set_conn")
                    idx = int(k) - 1
                    if 0 <= idx < len(_CAT_IDS):
                        drawer_sel = idx
                        if screen == "desktop" and hasattr(view, "desktop"):
                            view.desktop.set_strip_sel(idx)
                        elif screen == "drawer" and hasattr(view, "action_menu"):
                            view.action_menu.set_selected(idx)
                        _finish_menu_res(_run_action(_CAT_IDS[idx]))

                elif k in ("ESC", "BACK", "BACKSPACE"):
                    if screen == "drawer":
                        board.beep(1050, 10)
                        view = _mount_view("desktop")
                        status_msg = "Desktop Home"
                        status_kind = "info"
                        view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                        view.render(force=True)
                    elif hasattr(view, "desktop") and view.desktop.strip_sel is not None:
                        view.desktop.set_strip_sel(None)
                        board.beep(950, 8)
                        view.render(force=False)
                    else:
                        board.beep(900, 10)
                        status_msg = "Home Active (F1:Help L/R:Cat ENT:Apps)"
                        status_kind = "info"
                        view.footer_bar.update(status=status_msg, status_kind=status_kind)
                        view.render(force=False)

            anim_ticks += 1
            if anim_ticks >= 20:
                anim_ticks = 0
                bat_now = board.get_battery()
                if bat_now.get("charging") and bat_now.get("percent", 0) < 100:
                    chg_phase = (chg_phase + 1) & 3
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                    view.render(force=False)
            idle_ticks += 1
            if idle_ticks >= 40:
                idle_ticks = 0
                now_idle_ms = _ticks_ms()
                gc.collect()
                # MemGuard: reclaim stale modules / idle WebPortal before heap starvation (safe point: no tool active)
                _mf = gc.mem_free() if hasattr(gc, "mem_free") else 262144
                if _mf < 100000:
                    from core.memutil import reclaim
                    _lvl = 1
                    _fr = reclaim(1, runtime_state)
                    _mf = gc.mem_free()
                    if _mf < 60000:
                        _lvl = 2
                        _fr += reclaim(2, runtime_state)
                        _mf = gc.mem_free()
                    if _lvl != mg_level:
                        mg_level = _lvl
                        if logger:
                            logger.warn("MEMGUARD L{}: freed {}B -> free={}B".format(_lvl, _fr, _mf))
                    if _mf < 40000:
                        status_msg = "LOW MEMORY ({}KB) - close tools".format(_mf // 1024)
                        status_kind = "warn"
                elif _mf > 120000:
                    mg_level = 0
                    runtime_state["_mem_retry"] = False
                # Non-blocking background Wi-Fi auto-connect state machine (#8, #24, #47, #55)
                if runtime_state.get("wifi_bg_pending"):
                    runtime_state["wifi_bg_pending"] = False
                    try:
                        from net.wifi import get_wifi_manager
                        _wbg = get_wifi_manager()
                        _bok, _bmsg = _wbg.start_bg_connect(country=str(cfg.get("wifi_country", "XX") if cfg else "XX"), timeout_s=24)
                        if logger:
                            logger.info("WIFI BG: " + str(_bmsg))
                        if _bok and not _wbg.bg_active and (cfg is None or cfg.get("ntp_auto", True)):
                            runtime_state["ntp_pending"] = True
                            ntp_retries = 0
                            ntp_retry_at_ms = 0
                    except Exception as _we:
                        if logger:
                            logger.warn("WIFI BG: Start err: " + str(_we)[:48])
                else:
                    try:
                        _wmod = sys.modules.get("net.wifi")
                        if _wmod is not None and hasattr(_wmod, "get_wifi_manager"):
                            _wbg = _wmod.get_wifi_manager()
                            if _wbg.bg_active:
                                _bst, _bmsg = _wbg.step_bg_connect()
                                if _bst == "connected":
                                    if logger:
                                        logger.info("WIFI BG: " + str(_bmsg))
                                    if cfg is None or cfg.get("ntp_auto", True):
                                        runtime_state["ntp_pending"] = True
                                        ntp_retries = 0
                                        ntp_retry_at_ms = 0
                                elif _bst in ("timeout", "error"):
                                    if logger:
                                        logger.warn("WIFI BG: " + str(_bmsg))
                    except Exception as _we:
                        if logger:
                            logger.warn("WIFI BG: Step err: " + str(_we)[:48])

                # Periodic NTP resync + bounded backoff retry (#47)
                ntp_auto_on = bool(cfg.get("ntp_auto", True) if cfg else True)
                if ntp_auto_on and ntp_retry_at_ms and _ticks_diff(now_idle_ms, ntp_retry_at_ms) >= 0:
                    ntp_retry_at_ms = 0
                    runtime_state["ntp_pending"] = True
                elif ntp_auto_on and not runtime_state.get("ntp_pending"):
                    resync_s = int(cfg.get("ntp_resync_s", 3600) if cfg else 3600)
                    if resync_s > 0 and _ticks_diff(now_idle_ms, last_ntp_sync_ms) >= (resync_s * 1000):
                        _wmod = sys.modules.get("net.wifi")
                        if _wmod is not None and hasattr(_wmod, "get_wifi_manager"):
                            if _wmod.get_wifi_manager().status().get("connected"):
                                runtime_state["ntp_pending"] = True
                                ntp_retries = 0

                # Background NTP sync if queued (never blocks Wi-Fi connect or trips WDT)
                if runtime_state.get("ntp_pending"):
                    runtime_state["ntp_pending"] = False
                    if ntp_auto_on:
                        try:
                            feed_wdt()
                            from net.wifi import sync_ntp
                            from core.config import save_rtc_state
                            nok, nmsg = sync_ntp(
                                board=board,
                                tz_offset_h=int(cfg.get("tz_offset_h", 0) if cfg else 0),
                                host=str(cfg.get("ntp_server", "162.159.200.1") if cfg else "162.159.200.1"),
                                timeout_s=2,
                            )
                            feed_wdt()
                            if nok:
                                save_rtc_state(board)
                                last_ntp_sync_ms = _ticks_ms()
                                last_rtc_save_ms = last_ntp_sync_ms
                                ntp_retries = 0
                                ntp_retry_at_ms = 0
                                if logger:
                                    logger.info("NTP BG: OK " + str(nmsg))
                            else:
                                if logger:
                                    logger.warn("NTP BG: FAIL " + str(nmsg))
                                if ntp_retries < 2:
                                    ntp_retries += 1
                                    ntp_retry_at_ms = _ticks_ms() + (15000 if ntp_retries == 1 else 45000)
                        except Exception as _ne:
                            if logger:
                                logger.warn("NTP BG: ERR " + str(_ne)[:48])

                # Periodic RTC checkpoint to SD (gated >= 300s & year >= 2024 to avoid SD wear) (#55)
                rtc_int_s = max(300, int(cfg.get("rtc_save_interval_s", 300) if cfg else 300))
                if _ticks_diff(_ticks_ms(), last_rtc_save_ms) >= (rtc_int_s * 1000):
                    last_rtc_save_ms = _ticks_ms()
                    try:
                        from core.config import save_rtc_state
                        save_rtc_state(board)
                    except Exception:
                        pass

                # Refresh live top-bar clock & telemetry strip (dirty-only, zero flicker)
                view.sync(
                    board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind,
                    chg_phase=chg_phase, hints=_SHIFT_HINTS if last_shift_bar else _DESKTOP_HINTS,
                )
                view.render(force=False)
                # Check configurable auto-sleep timeout (suppressed when LNK or WebPortal WEB is active)
                st_s = int(cfg.get("sleep_timeout_s", 300) if cfg else 300)
                if runtime_state.get("serial_link") or runtime_state.get("web_active"):
                    last_act_ms = _ticks_ms()
                elif st_s > 0 and _ticks_diff(_ticks_ms(), last_act_ms) >= (st_s * 1000):
                    try:
                        from core.config import save_rtc_state
                        save_rtc_state(board)
                    except Exception:
                        pass
                    slept = _enter_sleep_mode(board, ui, logger, countdown_s=5)
                    last_act_ms = _ticks_ms()
                    view.sync(board, boot_state, BOOT_STABLE_MS, True, "Woke from Sleep" if slept else "Sleep Cancelled", "ok", chg_phase=chg_phase)
                    view.render(force=True)
            feed_wdt()
            if runtime_state.get("web_active"):
                step_webportal(20)
                _ws = runtime_state.get("web_server")
                if _ws is not None:
                    if _ws.pending_reboot:
                        _ws.pending_reboot = False
                        try:
                            from core.config import save_rtc_state
                            save_rtc_state(board)
                        except Exception:
                            pass
                        if logger:
                            logger.info("WEB: Remote reboot requested")
                            logger.clear_breadcrumb("CLEAN_EXIT")
                        stop_webportal(logger=logger)
                        board.reboot()
                    if _ws.pending_run:
                        _pr = _ws.pending_run
                        _ws.pending_run = None
                        _rpath = _pr[0]
                        _rlabel = _pr[1]
                        _needs_radio = bool(_pr[2]) if len(_pr) > 2 else False
                        if getattr(_ws, "_run_queued_ms", 0):
                            _qlat = _ticks_diff(_ticks_ms(), _ws._run_queued_ms)
                            try:
                                _ws._wlog("RUN_START {} lat={}ms".format(_rlabel, _qlat))
                            except Exception:
                                pass
                        _ws.set_run_state("running")
                        _paused_web = False
                        if _needs_radio and hasattr(_ws, "pause"):
                            _paused_web = _ws.pause()
                        gc.collect()
                        try:
                            status_msg, status_kind = _exec_sandbox_file(_rpath, _rlabel, wait_after=False)
                        finally:
                            if _paused_web and hasattr(_ws, "resume"):
                                _ws.resume()
                            _ws.set_run_state("done", runtime_state.get("_last_run_res"))
                        view = _mount_view()
                        view.sync(board, boot_state, BOOT_STABLE_MS, True, status_msg, status_kind, chg_phase=chg_phase)
                        view.render(force=True)
                        last_act_ms = _ticks_ms()
            else:
                if (idle_ticks & 1) == 0:
                    _w = runtime_state.get("_sta_wlan")
                    if _w is None:
                        try:
                            import network as _nw
                            _w = _nw.WLAN(_nw.STA_IF)
                            runtime_state["_sta_wlan"] = _w
                        except Exception:
                            _w = False
                            runtime_state["_sta_wlan"] = False
                    if _w:
                        try:
                            if _w.active() and _w.isconnected():
                                _w.status("rssi")
                        except Exception:
                            pass
                _sleep_ms(30)
    except KeyboardInterrupt:
        _stop_repl_watcher()
        stop_webportal(logger=logger)
        _start_repl_keepalive()
        runtime_state["serial_link"] = True
        if logger:
            try:
                logger.clear_breadcrumb("CLEAN_EXIT")
            except Exception:
                pass
        if hasattr(board, "init_uart_bridge"):
            board.init_uart_bridge(rebind=True)
        try:
            board.fill_rect(0, 294, 320, 26, 3)
            board.text("COM4 REPL ACTIVE (>>>) | Host Ready", 20, 303, 0)
            board.show()
        except Exception:
            pass
        bp("[UI] Interrupted via serial Ctrl+C; returning to REPL.")
    except MemoryError as mem_exc:
        gc.collect(); gc.collect()
        if not runtime_state.get("_mem_retry"):
            runtime_state["_mem_retry"] = True
            try:
                from core.memutil import reclaim
                _fr = reclaim(2, runtime_state)
            except Exception:
                _fr = 0
            gc.collect(); gc.collect()
            if logger:
                try:
                    logger.warn("UI: MemoryError recovered by MemGuard (freed {}B)".format(_fr))
                except Exception:
                    pass
            bp("[UI] MemoryError caught -> MemGuard reclaimed {}B, recovering UI".format(_fr))
            return ui_loop()
        runtime_state["_mem_retry"] = False
        choice = show_bsod(
            board,
            "UI_MEMORY_ERROR",
            mem_exc,
            context="mode={} theme={}".format(ui.mode, theme_mgr.active.id),
            interactive=True,
        )
        if choice in ("RECOVER", "LOGS"):
            return ui_loop()
    except Exception as ui_exc:
        if type(ui_exc).__name__ == "SoftWatchdogAbort":
            bp("[WDT] SoftWatchdogAbort -> returning to Desktop Home")
            theme_mgr._push_to_board(theme_mgr.active)
            return ui_loop(sel_action=0)
        choice = show_bsod(
            board,
            "UI_LOOP_EXCEPTION",
            ui_exc,
            context="mode={} theme={}".format(ui.mode, theme_mgr.active.id),
            interactive=True,
        )
        if choice in ("RECOVER", "LOGS"):
            saved_tid = cfg.get("theme", theme_mgr.active.id) if cfg else theme_mgr.active.id
            saved_mode = cfg.get("ui_mode", ui.mode) if cfg else ui.mode
            try:
                theme_mgr.apply(saved_tid, persist=False)
            except Exception:
                theme_mgr.apply("cyber_amber", persist=False)
            ui.set_mode(saved_mode, persist=False)
            if choice == "LOGS":
                open_log_viewer(board, ui, logger, kind="crash")
            return ui_loop(sel_action=0)
        if choice == "SAFE_MODE":
            return enter_safe_recovery_mode(board=board, state=boot_state, reason=repr(ui_exc), interactive=True)
        if hasattr(board, "init_uart_bridge"):
            board.init_uart_bridge(rebind=True)


_boot_splash_active = False


def _log_heap_stage(logger, stage):
    """Log post-GC free SRAM and largest contiguous block (96 KB cap) for boot/runtime timeline (#26)."""
    gc.collect()
    free_b = gc.mem_free() if hasattr(gc, "mem_free") else 0
    blk_b = 0
    try:
        from core.memutil import largest_free
        blk_b = largest_free(cap=98304)
    except Exception:
        pass
    msg = "HEAP[{}]: free={}B blk={}B".format(stage, free_b, blk_b)
    if logger:
        try:
            logger.info(msg)
        except Exception:
            pass
    bp("[HEAP]", msg)
    return free_b, blk_b


def _boot_progress(pct, msg, pause_ms=0, clear_splash=False):
    """Advance the frozen pinhos_boot splash progress bar in-place during cold boot."""
    global _boot_splash_active
    try:
        from core.memutil import largest_free
        bp("[BOOT {}%] {} (free={}B blk={}B)".format(pct, msg, gc.mem_free() if hasattr(gc, "mem_free") else 0, largest_free(cap=98304)))
    except Exception:
        pass
    if not _boot_splash_active:
        return
    try:
        import pinhos_boot as pb
        pb._splash_drawn = True
        pb.set_progress(pct, msg)
        if pause_ms > 0:
            _sleep_ms(pause_ms)
        if clear_splash:
            pb._splash_drawn = False
            _boot_splash_active = False
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
    _stop_repl_watcher()
    global _boot_splash_active
    _boot_splash_active = bool(interactive)

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
        _boot_progress(94, "Board HAL & SD Ready...", pause_ms=60)

        # Step 4: Initialize canonical /sd/pinhos/ filesystem hierarchy, core services & Dual-UI
        from core.config import ensure_canonical_dirs, load_version_manifest, ConfigManager, restore_rtc_state
        from core.logger import get_logger
        from core.swap import get_swap_manager
        from core.theme import get_theme_manager
        from ui.engine import UIEngine

        ensure_canonical_dirs()
        restore_rtc_state(board)
        manifest = load_version_manifest()
        cfg = ConfigManager()

        # Re-sync board profile, CPU clock (safe-guarded), & backlights from loaded config
        desired_board = cfg.get("board", "picocalc")
        if desired_board != board.id:
            board = get_board(profile=desired_board, config=cfg.as_dict(), force_new=True)
            runtime_state["board"] = board
        board.set_backlight(cfg.get("lcd_brightness", 80))
        board.set_kb_backlight(cfg.get("kb_brightness", 60))
        if hasattr(board, "config") and isinstance(board.config, dict):
            board.config["sound"] = bool(cfg.get("sound", True))
        try:
            import machine
            req_mhz = int(cfg.get("cpu_freq_mhz", 150))
            if boot_state.get("boot_strikes", 0) >= 2 and req_mhz > 150:
                req_mhz = 150
            if 50 <= req_mhz <= 260 and (machine.freq() // 1000000) != req_mhz:
                machine.freq(req_mhz * 1000000)
                if hasattr(board, "init_uart_bridge"):
                    board.init_uart_bridge(rebind=True)
        except Exception:
            pass

        # Mirror boot_state onto SD now that /sd is mounted
        if state_path is None:
            save_boot_state(boot_state)

        logger = get_logger()
        prev_crash = logger.check_previous_crash()
        runtime_state["prev_crash"] = prev_crash
        logger.set_breadcrumb("BOOT_INIT", "services")
        swap = get_swap_manager()
        swap.set_max_kb(int(cfg.get("swap_max_kb", 512)))
        swap.prune_stale()
        if hasattr(board, "prune_screenshots"):
            board.prune_screenshots(keep=5)
        if hasattr(gc, "threshold"):
            try:
                gc.threshold(16384)
            except Exception:
                pass
        try:
            import core.memutil  # Pre-import early to pack at bottom of heap (#20)
        except Exception:
            pass

        _boot_progress(94, "Core Services Ready...", pause_ms=80)

        # Interactive-session hooks (wifi_bg_pending, enable_wdt, webportal_autostart)
        # are initialized idempotently on ui_loop() entry via _init_interactive_services() (#29).
        runtime_state["_interactive_init_done"] = False
        runtime_state["_standalone_boot"] = bool(interactive)

        # Show clean 100% on native monochrome boot splash, cut cleanly to black BEFORE applying theme LUT!
        _boot_progress(100, "PinhOS Ready!", pause_ms=400, clear_splash=True)
        try:
            board.fill(0)
            board.show()
        except Exception:
            pass
        gc.collect()

        theme_mgr = get_theme_manager(config=cfg, board=board, force_new=True)
        ui = UIEngine(board=board, theme_manager=theme_mgr, config=cfg)

        runtime_state["manifest"] = manifest
        runtime_state["config"] = cfg
        runtime_state["logger"] = logger
        runtime_state["swap"] = swap
        runtime_state["theme"] = theme_mgr
        runtime_state["ui"] = ui
        runtime_state["sandbox"] = None
        _register_recovery_helpers()

        try:
            from core.logger import get_boot_id
            _bid = get_boot_id()
        except Exception:
            _bid = 0
        boot_msg = "BOOT: PinhOS v{} ({}) boot_id=b{} starting on {} [{} / {}]".format(
            manifest.get("version", "1.0.0-alpha.5.0"),
            manifest.get("arch", "armv7emsp"),
            _bid,
            board.name,
            ui.mode_badge,
            theme_mgr.active.id,
        )
        logger.info(boot_msg)
        bp("[BOOT]", boot_msg)

        # Step 5: Render initial Desktop Home (or App Drawer) and monitor 5-second stability window
        boot_scr = str(cfg.get("boot_screen", "desktop")).lower()
        if boot_scr == "drawer":
            view = _DashboardView(ui, manifest, sel_action=0, layout=str(cfg.get("launcher_layout", "grid")).lower())
        else:
            view = _DesktopView(ui, manifest)
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
        free_b, _ = _log_heap_stage(logger, "BOOT_OK")
        bp("<<PINHOS:BOOT_OK:v{}:FREE_RAM={}>>".format(
            manifest.get("version", "1.0.0-alpha.5.0"), free_b
        ))
        if interactive:
            if prev_crash and prev_crash.get("wdt_reset"):
                try:
                    from ui.widgets import Dialog
                    _op = str(prev_crash.get("op", "IDLE"))
                    _det = str(prev_crash.get("detail", ""))
                    _kb = int(prev_crash.get("free_kb", 0))
                    _dlg = Dialog(
                        16, 68, 288, 168,
                        title="WATCHDOG RESET RECOVERED",
                        lines=[
                            "Previous session timed out (>8s)",
                            "and was safely restarted by WDT.",
                            "Last Op: {} {}".format(_op, ("(" + _det + ")") if _det else "")[:38],
                            "SRAM before reset: {} KB".format(_kb),
                            "See [CTRL+L] -> wdt.log for details.",
                        ],
                        footer="[ANY KEY] Continue to Desktop",
                        kind="warn",
                    )
                    ui.add_widget(_dlg)
                    ui.render(force=False)
                    board.clear_input()
                    _pf = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
                    while True:
                        feed_wdt()
                        if _pf and _pf() is not None:
                            board.beep(1200, 12)
                            break
                        _sleep_ms(30)
                    ui.remove_widget(_dlg)
                    ui.mark_all_dirty(True)
                    board.clear_input()
                except Exception:
                    pass
            ui_loop()
        return {
            "mode": "NORMAL",
            "ui_mode": ui.mode,
            "theme": theme_mgr.active.id,
            "version": manifest.get("version", "1.0.0-alpha.5.0"),
            "board": board.id,
            "stabilized": runtime_state["stabilized"],
            "strikes": boot_state.get("boot_strikes", 0),
            "free_sram": free_b,
        }

    except Exception as exc:
        err_msg = repr(exc)
        boot_state["last_error"] = err_msg[:120]
        save_boot_state(boot_state, state_path=state_path)
        b_ref = runtime_state.get("board")
        if b_ref is not None and hasattr(b_ref, "init_uart_bridge"):
            try:
                b_ref.init_uart_bridge(rebind=True)
            except Exception:
                pass
        if runtime_state.get("logger"):
            runtime_state["logger"].exception("BOOT", exc)
        if boot_state.get("boot_strikes", 0) >= int(boot_state.get("strike_limit", STRIKE_LIMIT)):
            return enter_safe_recovery_mode(
                board=b_ref,
                state=boot_state,
                reason=err_msg,
                state_path=state_path,
                interactive=interactive,
            )
        if interactive and b_ref is not None:
            choice = show_bsod(b_ref, "BOOT_EXCEPTION", exc, context="start()", interactive=True)
            if choice == "SAFE_MODE":
                return enter_safe_recovery_mode(board=b_ref, state=boot_state, reason=err_msg, state_path=state_path, interactive=True)
            return {"mode": "BSOD_REPL", "error": err_msg}
        raise


if __name__ == "__main__":
    start(
        skip_strike_increment=bool(globals().get("_FLASH_GUARD_ACTIVE", False)),
        interactive=True,
    )

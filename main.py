# PinhOS v1.0.0-alpha.1 — Phase 1 Boot Entry, 3-Strike Crash Guard & Safe Recovery Mode (main.py)
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


_PHASE1_ACTIONS = (
    "Run 6/6 On-Device Self-Test",
    "Run Sandbox App: Hello PinhOS",
    "Run Sandbox App: Matrix Rain",
    "Refresh Telemetry & Beep",
)


def _draw_phase1_boot_screen(board, manifest, boot_state, elapsed_ms, stabilized, sel_action=0, status_msg=""):
    """Render the Phase 1 foundation status & interactive launcher screen on the 320x320 display."""
    if board is None:
        return
    try:
        gc.collect()
        board.recover_refresh()
        free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        bat = board.get_battery()
        sd_stats = board.get_sd_stats()
        ver = manifest.get("version", "1.0.0-alpha.1")
        arch = manifest.get("arch", "armv7emsp")

        board.fill(0)
        # Top Header Bar
        board.fill_rect(0, 0, 320, 22, 3)
        board.text("PinhOS v{} [{}]".format(ver, arch), 8, 7, 0)

        # Main Frame
        board.rect(4, 25, 312, 242, 3)
        board.text("PHASE 1: HAL, BOOT GUARD & SANDBOX", 16, 33, 3)
        board.hline(8, 45, 304, 6)

        strikes = boot_state.get("boot_strikes", 0)
        if stabilized:
            guard_str = "STABLE (0/3 CLEARED)"
            guard_col = 10
        else:
            rem_s = max(0, (BOOT_STABLE_MS - elapsed_ms + 999) // 1000)
            guard_str = "ARMED ({}/3 - {}s)".format(strikes, rem_s)
            guard_col = 11

        sd_str = "MOUNTED ({} MB Free)".format(sd_stats["free_kb"] // 1024) if sd_stats["mounted"] else "UNMOUNTED"
        bat_str = "{}% ({} mV{})".format(
            bat["percent"],
            bat["voltage_mv"],
            " CHG" if bat["charging"] else "",
        )
        board_label = "PicoCalc (RP2350)" if board.id == "picocalc" else board.name
        val_x = 112
        max_val_chars = max(16, (board.display_width - 14 - val_x) // 8)

        rows = [
            ("BOARD HAL  :", board_label, 15),
            ("DISPLAY    :", "{}x{} RGB565 LUT".format(board.display_width, board.display_height), 15),
            ("SD STORAGE :", sd_str, 10 if sd_stats["mounted"] else 9),
            ("BOOT GUARD :", guard_str, guard_col),
            ("FREE SRAM  :", "{} KB / 520 KB".format(free_kb), 14),
            ("BATTERY    :", bat_str, 15),
            ("BACKLIGHT  :", "LCD {}% / KB {}%".format(board.get_backlight(), board.get_kb_backlight()), 15),
            ("CPU TEMP   :", "{} C | RTC {}".format(board.get_cpu_temp_c(), board.get_timestamp_str(True)), 15),
        ]

        y = 53
        for label, val, col in rows:
            board.text(label, 12, y, 3)
            board.text(str(val)[:max_val_chars], val_x, y, col)
            y += 19

        # Interactive Action Selector Box
        board.hline(8, 208, 304, 6)
        act_lbl = _PHASE1_ACTIONS[sel_action % len(_PHASE1_ACTIONS)]
        board.text("ACTION [{}/{}]:".format((sel_action % len(_PHASE1_ACTIONS)) + 1, len(_PHASE1_ACTIONS)), 12, 215, 3)
        board.fill_rect(10, 229, 300, 18, 3)
        board.text("> " + act_lbl[:34], 14, 234, 0)
        if status_msg:
            board.text(str(status_msg)[:37], 12, 252, 10)
        else:
            board.text("[1]Hello [2]Matrix [T]Test [R]Refresh", 12, 252, 14)

        # Footer Bar
        board.fill_rect(0, 272, 320, 48, 0)
        board.fill_rect(0, 272, 320, 22, 8)
        board.text("UP/DN:Select  ENT/SPC:Run  Q:REPL", 16, 279, 15)
        board.fill_rect(0, 294, 320, 26, 3)
        board.text("COM4 Ready | Run: .\\picocalc.ps1 test", 12, 303, 0)
        board.show()
    except Exception as e:
        bp("DRAW_ERR:", repr(e))


def ui_loop(sel_action=0):
    """
    Interactive Phase 1 keyboard event loop.
    Polls STM32 I2C keyboard without starving Core 1 LCD refresh, keeps UART0 dupterm
    active, and cleanly exits to REPL on ESC/Backspace/Q or serial Ctrl+C (\\x03).
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

    manifest = runtime_state.get("manifest") or {"version": "1.0.0-alpha.1", "arch": "armv7emsp"}
    boot_state = runtime_state.get("boot_state") or load_boot_state()
    sandbox = runtime_state.get("sandbox")
    status_msg = ""

    def _drain_keys(delay_ms=150):
        _sleep_ms(delay_ms)
        board.clear_input()
        pf = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
        if pf:
            for _ in range(8):
                if pf() is None:
                    break
        board.clear_input()

    board.clear_input()
    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

    try:
        while True:
            poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
            key = poll_fn() if poll_fn else None
            if key:
                k = str(key).upper()
                if k == "Q":
                    board.beep(800, 15)
                    bp("[UI] Exiting Phase 1 loop to REPL (key=Q)")
                    board.fill_rect(0, 272, 320, 48, 0)
                    board.fill_rect(0, 272, 320, 22, 8)
                    board.text("EXITED TO REPL (COM4) | _pm.ui_loop()", 12, 279, 15)
                    board.fill_rect(0, 294, 320, 26, 10)
                    board.text("REPL ACTIVE (>>>) | UART0 READY", 24, 303, 0)
                    board.show()
                    break

                elif k in ("ESC", "BACK", "BACKSPACE"):
                    board.beep(900, 10)
                    status_msg = "Dashboard Active (Press Q for REPL)"
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

                elif k in ("UP", "LEFT"):
                    sel_action = (sel_action - 1) % len(_PHASE1_ACTIONS)
                    board.beep(1100, 10)
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

                elif k in ("DOWN", "RIGHT"):
                    sel_action = (sel_action + 1) % len(_PHASE1_ACTIONS)
                    board.beep(1100, 10)
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

                elif k in ("T", "F2") or (k in ("ENTER", "SPACE", " ") and sel_action == 0):
                    board.beep(1400, 15)
                    _drain_keys(120)
                    import tests.selftest as _st
                    res = _st.run_all(interactive_wait=True)
                    _drain_keys(150)
                    status_msg = "Self-Test {}/{} {}".format(
                        res.get("passed", 0), res.get("total", 6), "PASS" if res.get("ok") else "FAIL"
                    )
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

                elif k == "1" or (k in ("ENTER", "SPACE", " ") and sel_action == 1):
                    board.beep(1400, 15)
                    _drain_keys(120)
                    if sandbox is not None:
                        res = sandbox.run_file("/sd/pinhos/apps/hello_world.py", wait_on_error=True)
                        status_msg = "Hello OK (delta={}B)".format(res.get("sram_delta", 0))
                        if res.get("ok"):
                            board.clear_input()
                            while True:
                                ak = poll_fn() if poll_fn else None
                                if ak is not None:
                                    board.beep(1100, 10)
                                    break
                                _sleep_ms(30)
                    _drain_keys(150)
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

                elif k == "2" or (k in ("ENTER", "SPACE", " ") and sel_action == 2):
                    board.beep(1400, 15)
                    _drain_keys(120)
                    if sandbox is not None:
                        res = sandbox.run_file("/sd/pinhos/apps/matrix_deck.py", wait_on_error=True)
                        status_msg = "Matrix OK (delta={}B)".format(res.get("sram_delta", 0))
                    _drain_keys(150)
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

                elif k in ("R", "F1") or (k in ("ENTER", "SPACE", " ") and sel_action == 3):
                    board.beep(1600, 15)
                    status_msg = "Telemetry Refreshed @ " + board.get_timestamp_str(True)
                    _draw_phase1_boot_screen(board, manifest, boot_state, BOOT_STABLE_MS, True, sel_action, status_msg)

            _sleep_ms(30)
    except KeyboardInterrupt:
        if hasattr(board, "init_uart_bridge"):
            board.init_uart_bridge()
        bp("[UI] Interrupted via serial Ctrl+C; returning to REPL.")


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
    Main Phase 1 boot sequence:
    1. Increment persistent boot_strikes in flash BEFORE mounting SD or loading modules.
    2. Enter Safe Recovery Mode immediately if boot_strikes >= 3.
    3. Initialize Board HAL, mount /sd with retry, and create canonical /sd/pinhos/ dirs.
    4. Initialize ConfigManager, Logger, SwapManager, and SandboxRunner.
    5. Run startup stabilization window (>5s) and clear boot_strikes = 0 once stable.
    6. Optionally enter interactive keyboard UI loop (ui_loop) while keeping UART0 dupterm active.
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
        _boot_progress(95, "Board HAL & SD Ready...")

        # Step 4: Initialize canonical /sd/pinhos/ filesystem hierarchy & core services
        from core.config import ensure_canonical_dirs, load_version_manifest, ConfigManager
        from core.logger import get_logger
        from core.swap import get_swap_manager
        from core.sandbox import SandboxRunner

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
        swap = get_swap_manager()
        swap.prune_stale()
        sandbox = SandboxRunner(board=board, config=cfg, swap=swap, logger=logger)

        runtime_state["manifest"] = manifest
        runtime_state["config"] = cfg
        runtime_state["logger"] = logger
        runtime_state["swap"] = swap
        runtime_state["sandbox"] = sandbox
        _register_recovery_helpers()

        boot_msg = "BOOT: PinhOS v{} ({}) starting on {}".format(
            manifest.get("version", "1.0.0-alpha.1"),
            manifest.get("arch", "armv7emsp"),
            board.name,
        )
        logger.info(boot_msg)
        bp("[BOOT]", boot_msg)
        _boot_progress(100, "PinhOS Ready!", pause_ms=180, clear_splash=True)

        # Step 5: Render initial boot screen and monitor 5-second stability window
        elapsed = _ticks_diff(_ticks_ms(), t0)
        _draw_phase1_boot_screen(board, manifest, boot_state, elapsed, False)

        if wait_for_stability:
            last_draw_s = -1
            while True:
                now = _ticks_ms()
                elapsed = _ticks_diff(now, t0)
                if check_boot_stability(elapsed, state_path=state_path):
                    boot_state = load_boot_state(state_path=state_path)
                    runtime_state["boot_state"] = boot_state
                    runtime_state["stabilized"] = True
                    _draw_phase1_boot_screen(board, manifest, boot_state, elapsed, True)
                    logger.info("BOOT GUARD: Stabilized after {}ms; boot_strikes=0".format(elapsed))
                    bp("[BOOT_GUARD] Stabilized after {}ms (boot_strikes=0)".format(elapsed))
                    break

                cur_s = elapsed // 1000
                if cur_s != last_draw_s:
                    last_draw_s = cur_s
                    _draw_phase1_boot_screen(board, manifest, boot_state, elapsed, False)
                    bp("[BOOT_GUARD] Stabilizing {}/5s (strike {}/{})...".format(
                        cur_s + 1,
                        boot_state.get("boot_strikes", 1),
                        boot_state.get("strike_limit", STRIKE_LIMIT),
                    ))
                _sleep_ms(100)
        else:
            runtime_state["stabilized"] = (boot_state.get("boot_strikes", 0) == 0)
            _draw_phase1_boot_screen(board, manifest, boot_state, elapsed, runtime_state["stabilized"])

        gc.collect()
        free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        bp("<<PINHOS:BOOT_OK:v{}:FREE_RAM={}>>".format(
            manifest.get("version", "1.0.0-alpha.1"), free_b
        ))
        if interactive:
            ui_loop()
        return {
            "mode": "NORMAL",
            "version": manifest.get("version", "1.0.0-alpha.1"),
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

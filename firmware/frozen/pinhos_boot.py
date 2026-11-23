# PinhOS Frozen Boot Router & Dual-Boot Manager (pinhos_boot.py)
# Decoupled from hardcoded versions (reads /sd/pinhos/version.json), with live
# hotkey countdown, staged cold-boot progress bar, and crash-proof Boot Menu.

import gc
import json
import os
import sys
import time

VERSION_JSON_PATHS = ("/sd/pinhos/version.json", "/version.json")
BOOT_STATE_PATHS = ("/sd/pinhos/boot_state.json", "/boot_state.json")
BOOT_TARGET_PATHS = ("/sd/pinhos/boot_target.json", "/boot_target.json")

UF2_VERSION = "1.0.1_build20112026"

_cached_ver = None
_splash_drawn = False
_ctrl_held = False


def _load_version_info():
    """Read OS version and firmware_version from /sd/pinhos/version.json with safe fallback."""
    global _cached_ver
    if _cached_ver is not None:
        return _cached_ver
    os_ver = "SD-RECOVERY"
    fw_ver = UF2_VERSION
    for p in VERSION_JSON_PATHS:
        try:
            with open(p, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                v = data.get("version")
                if isinstance(v, str) and v.strip():
                    os_ver = v.strip()
                fv = data.get("firmware_version")
                if isinstance(fv, str) and fv.strip():
                    fw_ver = fv.strip()
                break
        except Exception:
            pass
    _cached_ver = (os_ver, fw_ver)
    return _cached_ver


def get_version_str():
    os_ver, _ = _load_version_info()
    return os_ver


def _poll_hotkey(kb=None):
    """Non-blocking STM32 keyboard poll via picocalc.keyboard.keyEvent() (tracks Ctrl 0xA5)."""
    global _ctrl_held
    if kb is None:
        try:
            import picocalc
            kb = getattr(picocalc, "keyboard", None)
        except Exception:
            kb = None
    if kb is None or not hasattr(kb, "keyEvent"):
        return None
    try:
        for _ in range(4):
            ev = kb.keyEvent()
            if not ev or len(ev) < 2:
                return None
            state = ev[0]
            code = ev[1]
            if state in (0, 0xFF) or code in (0, 0xFF):
                return None
            if code == 0xA5:
                _ctrl_held = (state in (1, 2))
                continue
            if state == 3:
                continue
            if state in (1, 2):
                if code == 0x03 or (_ctrl_held and code in (0x63, 0x43)):
                    return "CTRL_C"
                if code in (0xB1, 0x1B):
                    return "ESC"
                if code == 0x81:
                    return "F1"
                if code == 0x82:
                    return "F2"
                if code in (0x0A, 0x0D):
                    return "ENTER"
                if code == 0xB5:
                    return "UP"
                if code == 0xB6:
                    return "DOWN"
                if 32 <= code <= 126:
                    return chr(code).upper()
    except Exception as e:
        print("[BOOT_KB_ERR]", repr(e))
    return None


def _draw_splash_frame(os_ver, fw_ver, sub="[F1]Recov [F2]Menu [ENT]Boot", sub2="[CTRL+C] Interrupt to REPL"):
    """Draw static boot splash chrome once (avoids repeated full-screen redraws)."""
    global _splash_drawn
    try:
        import picocalc
        d = picocalc.display
        if not _splash_drawn:
            d.recoverRefresh()
        d.fill(0)
        d.rect(10, 68, 300, 184, 15)
        d.fill_rect(12, 70, 296, 26, 15)
        hdr = "PinhOS v" + os_ver
        hx = max(16, (320 - len(hdr) * 8) // 2)
        d.text(hdr[:34], hx, 79, 0)
        d.text("ClockworkPi PicoCalc (RP2350)", 40, 110, 15)
        d.text(("UF2: " + fw_ver)[:34], 24, 126, 7)
        # Progress bar outline (inner 268x10 at x=26, y=166)
        d.rect(24, 164, 272, 14, 15)
        d.hline(18, 206, 284, 7)
        sx1 = max(16, (320 - len(sub[:36]) * 8) // 2)
        d.text(sub[:36], sx1, 215, 7)
        if sub2:
            sx2 = max(16, (320 - len(sub2[:36]) * 8) // 2)
            d.text(sub2[:36], sx2, 232, 7)
        d.show()
        _splash_drawn = True
    except Exception as e:
        print("[BOOT_SPLASH_ERR]", repr(e))


def set_progress(pct, status_msg="", sub=None):
    """Update only the status line and progress bar on the boot splash (0..100%)."""
    try:
        import picocalc
        d = picocalc.display
        if not _splash_drawn:
            os_ver, fw_ver = _load_version_info()
            _draw_splash_frame(os_ver, fw_ver, sub or "[F1]Recov [F2]Menu [ENT]Boot")
        p = max(0, min(100, int(pct)))
        # Clear and update status line
        d.fill_rect(18, 144, 284, 14, 0)
        if status_msg:
            d.text(str(status_msg)[:34], 24, 146, 7)
        # Clear and fill progress bar interior
        d.fill_rect(26, 166, 268, 10, 0)
        fill_w = (p * 268) // 100
        if fill_w > 0:
            d.fill_rect(26, 166, fill_w, 10, 15)
        # Update percentage readout
        d.fill_rect(18, 184, 284, 14, 0)
        pct_txt = "{}%".format(p)
        d.text(pct_txt, (320 - len(pct_txt) * 8) // 2, 186, 15)
        if sub is not None:
            d.fill_rect(14, 212, 292, 34, 0)
            s = str(sub)[:36]
            sx = max(16, (320 - len(s) * 8) // 2)
            d.text(s, sx, 222, 7)
        d.show()
    except Exception as e:
        print("[BOOT_PROG_ERR]", repr(e))


def _load_boot_target():
    for p in BOOT_TARGET_PATHS:
        try:
            with open(p, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"target": "pinhos"}


def _reset_boot_strikes():
    st = {"boot_strikes": 0, "strike_limit": 3, "safe_mode": False, "last_error": ""}
    for p in BOOT_STATE_PATHS:
        try:
            with open(p, "w") as f:
                json.dump(st, f)
        except Exception:
            pass


def _show_boot_menu(kb):
    """
    Crash-proof Interactive Dual-Boot Manager (Phase 7 ready):
    - Draws static chrome once (no repeated recoverRefresh() calls)
    - Dirty-flag rendering: only redraws menu rows when selection/note changes
    - Periodic gc.collect() + try/except logging over COM4
    """
    global _splash_drawn
    _splash_drawn = False
    os_ver, _ = _load_version_info()
    items = (
        ("1", "PinhOS (/sd/pinhos/main.py)", "pinhos"),
        ("2", "PinhOS Safe Recovery Mode", "recovery"),
        ("3", "Reset Strikes & Boot PinhOS", "reset_pinhos"),
        ("4", "UF2 Chainloader (/sd/firmwares)", "uf2_scan"),
    )
    sel = 0
    note = "Select boot target..."

    try:
        import picocalc
        d = picocalc.display
        d.fill(0)
        d.fill_rect(0, 0, 320, 24, 15)
        d.text(("PinhOS BOOT MGR v" + os_ver)[:36], 16, 8, 0)
        d.rect(6, 30, 308, 252, 15)
        d.fill_rect(0, 294, 320, 26, 8)
        d.text("UP/DN:Select  ENT:Boot  ESC:Recov", 20, 303, 15)
        d.show()
    except Exception as e:
        print("[BOOT_MENU_CHROME_ERR]", repr(e))

    def _render_rows(cur_sel, cur_note):
        try:
            import picocalc
            d = picocalc.display
            # Redraw only inner menu rows & status area (no fill(0), no recoverRefresh())
            d.fill_rect(10, 40, 300, 236, 0)
            y = 48
            for idx in range(len(items)):
                num, label, _ = items[idx]
                if idx == cur_sel:
                    d.fill_rect(12, y - 4, 296, 20, 15)
                    d.text("> [{}] {}".format(num, label[:29]), 16, y + 2, 0)
                else:
                    d.text("  [{}] {}".format(num, label[:29]), 16, y + 2, 15)
                y += 34
            if cur_note:
                d.hline(14, 218, 292, 7)
                d.text(str(cur_note)[:35], 16, 232, 7)
            d.show()
        except Exception as e:
            print("[BOOT_MENU_DRAW_ERR]", repr(e))

    dirty = True
    ticks = 0
    while True:
        try:
            if dirty:
                _render_rows(sel, note)
                dirty = False
                gc.collect()

            k = _poll_hotkey(kb)
            if k is not None:
                if k == "CTRL_C":
                    raise KeyboardInterrupt()
                if k == "ESC":
                    return "recovery"
                elif k == "UP":
                    new_sel = (sel - 1) % len(items)
                    if new_sel != sel:
                        sel = new_sel
                        dirty = True
                elif k == "DOWN":
                    new_sel = (sel + 1) % len(items)
                    if new_sel != sel:
                        sel = new_sel
                        dirty = True
                elif k in ("1", "2", "3", "4"):
                    choice = items[int(k) - 1][2]
                    if choice == "uf2_scan":
                        try:
                            fws = [f for f in os.listdir("/sd/firmwares") if f.endswith(".uf2")]
                            note = "Found {} UF2s (Phase 7)".format(len(fws))
                        except Exception:
                            note = "No /sd/firmwares/ directory"
                        dirty = True
                    else:
                        return choice
                elif k == "ENTER":
                    choice = items[sel][2]
                    if choice == "uf2_scan":
                        try:
                            fws = [f for f in os.listdir("/sd/firmwares") if f.endswith(".uf2")]
                            note = "Found {} UF2s (Phase 7)".format(len(fws))
                        except Exception:
                            note = "No /sd/firmwares/ directory"
                        dirty = True
                    else:
                        return choice

            ticks += 1
            if ticks >= 30:
                ticks = 0
                gc.collect()
            time.sleep_ms(30)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print("[BOOT_MENU_ERR]", repr(e))
            gc.collect()
            time.sleep_ms(50)


def _ensure_pinhos_path():
    if "/sd/pinhos" in sys.path:
        sys.path.remove("/sd/pinhos")
    sys.path.insert(0, "/sd/pinhos")


def _launch_recovery():
    set_progress(90, "Entering Safe Recovery Mode...")
    _ensure_pinhos_path()
    try:
        import main as _pm
        _pm.enter_safe_recovery_mode(reason="User requested Recovery Mode", interactive=True)
    except Exception as e:
        set_progress(100, "Recovery (COM4): " + repr(e)[:18])
        print("[PinhOS] Recovery fallback:", repr(e))


def _launch_pinhos():
    set_progress(80, "Loading /sd/pinhos/main.py...")
    _ensure_pinhos_path()
    try:
        os.stat("/sd/pinhos/main.py")
    except Exception:
        set_progress(100, "SD /sd/pinhos/main.py missing!", "COM4 Serial REPL Active")
        print("[PinhOS] /sd/pinhos/main.py not found; COM4 REPL active.")
        return

    gc.collect()
    import main as _pm
    set_progress(92, "Starting Boot Guard & HAL...")
    _pm.start(skip_strike_increment=False, interactive=True)


def boot():
    global _splash_drawn
    _splash_drawn = False

    kb = None
    try:
        import picocalc
        kb = getattr(picocalc, "keyboard", None)
    except Exception:
        kb = None

    # Stage 1 (15%): Hardware ready, draw splash
    os_ver, fw_ver = _load_version_info()
    _draw_splash_frame(os_ver, fw_ver, "[F1]Recov [F2]Menu [ENT]Boot")
    set_progress(15, "Hardware & UART0 Ready...")

    # Stage 2 (35%): Confirm SD mounted
    try:
        os.listdir("/sd")
        set_progress(35, "MicroSD Mounted (/sd)...")
    except Exception:
        set_progress(35, "MicroSD Check Skipped...")

    # Stage 3 (50%): Manifest loaded
    set_progress(50, "Manifest v" + os_ver + " Loaded")

    # Wait 120ms for STM32 southbridge post-reset settle and drain stale keys
    time.sleep_ms(120)
    for _ in range(8):
        if _poll_hotkey(kb) is None:
            break

    # Stage 4 (50% -> 75%): Live 5.0s hotkey countdown window ([ENTER] boots immediately)
    choice = None
    total_ms = 5000
    t_start = time.ticks_ms()
    last_tenths = -1

    while True:
        elapsed = time.ticks_diff(time.ticks_ms(), t_start)
        rem_ms = total_ms - elapsed
        if rem_ms <= 0:
            set_progress(75, "Booting in 0.0s...")
            break

        tenths = (rem_ms + 99) // 100
        if tenths != last_tenths:
            last_tenths = tenths
            pct = 50 + ((elapsed * 25) // total_ms)
            set_progress(pct, "Booting in {}.{}s...".format(tenths // 10, tenths % 10))

        k = _poll_hotkey(kb)
        if k == "CTRL_C":
            set_progress(100, "Boot Interrupted -> REPL", "REPL ACTIVE (>>>) | COM4 READY")
            print("[PinhOS] Boot interrupted (Ctrl+C) -> REPL")
            return
        if k == "ENTER":
            set_progress(75, "Booting PinhOS...")
            break
        if k in ("ESC", "F1"):
            choice = "recovery"
            break
        if k == "F2":
            choice = _show_boot_menu(kb)
            break
        time.sleep_ms(30)

    if choice is None:
        cfg = _load_boot_target()
        choice = str(cfg.get("target", "pinhos")).lower()

    if choice == "recovery":
        _launch_recovery()
        return

    if choice == "reset_pinhos":
        _reset_boot_strikes()

    _launch_pinhos()


if __name__ == "__main__":
    try:
        boot()
    except KeyboardInterrupt:
        print("[PinhOS] Boot interrupted -> COM4 REPL")
    except Exception as _exc:
        print("[PinhOS] Boot error:", repr(_exc))

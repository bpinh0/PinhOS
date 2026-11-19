# PinhOS Frozen Boot Router & Dual-Boot Stub (pinhos_boot.py)
# Prepared for Phase 1 Cold-Boot AND Phase 7 Multi-UF2 / Dual-Boot Chainloader.

import gc
import json
import os
import sys
import time
import machine

UF2_VERSION = "v1.0.0-uf2.2"
BOOT_STATE_PATHS = ("/sd/pinhos/boot_state.json", "/boot_state.json")
BOOT_TARGET_PATHS = ("/sd/pinhos/boot_target.json", "/boot_target.json")


def _poll_hotkey(kb=None):
    """Non-blocking STM32 keyboard poll via picocalc.keyboard.keyEvent()."""
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
            state, code = ev[0], ev[1]
            if state in (0, 0xFF) or code in (0, 0xFF):
                return None
            if state == 3:
                continue
            if state in (1, 2):
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
    except Exception:
        pass
    return None


def _draw_splash(msg="Booting PinhOS...", sub="[ESC/F1] Recovery  [F2] Boot Menu"):
    try:
        import picocalc
        d = picocalc.display
        d.recoverRefresh()
        d.fill(0)
        d.rect(10, 82, 300, 156, 3)
        d.fill_rect(12, 84, 296, 26, 3)
        d.text("PinhOS UF2 " + UF2_VERSION, 64, 93, 0)
        d.text("ClockworkPi PicoCalc (RP2350)", 40, 128, 15)
        d.text(msg[:34], 24, 156, 10)
        d.hline(18, 184, 284, 6)
        d.text(sub[:36], 18, 198, 14)
        d.show()
    except Exception:
        pass


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
    """Interactive Dual-Boot Manager (Phase 7 ready)."""
    items = (
        ("1", "PinhOS (/sd/pinhos/main.py)", "pinhos"),
        ("2", "PinhOS Safe Recovery Mode", "recovery"),
        ("3", "Reset Strikes & Boot PinhOS", "reset_pinhos"),
        ("4", "UF2 Chainloader (/sd/firmwares)", "uf2_scan"),
    )
    sel = 0

    def _render(note=""):
        try:
            import picocalc
            d = picocalc.display
            d.recoverRefresh()
            d.fill(0)
            d.fill_rect(0, 0, 320, 24, 3)
            d.text("PinhOS BOOT MGR " + UF2_VERSION, 32, 8, 0)
            d.rect(6, 30, 308, 236, 3)
            y = 48
            for idx, (num, label, _) in enumerate(items):
                if idx == sel:
                    d.fill_rect(12, y - 4, 296, 20, 3)
                    d.text("> [{}] {}".format(num, label[:29]), 16, y + 2, 0)
                else:
                    d.text("  [{}] {}".format(num, label[:29]), 16, y + 2, 15)
                y += 32
            if note:
                d.text(note[:36], 16, 236, 14)
            d.fill_rect(0, 294, 320, 26, 8)
            d.text("UP/DN:Select  ENT:Boot  ESC:Recov", 20, 303, 15)
            d.show()
        except Exception:
            pass

    _render("Select boot target...")
    while True:
        k = _poll_hotkey(kb)
        if k == "ESC":
            return "recovery"
        if k == "UP":
            sel = (sel - 1) % len(items)
            _render()
        elif k == "DOWN":
            sel = (sel + 1) % len(items)
            _render()
        elif k in ("1", "2", "3", "4"):
            choice = items[int(k) - 1][2]
            if choice == "uf2_scan":
                try:
                    fws = [f for f in os.listdir("/sd/firmwares") if f.endswith(".uf2")]
                    _render("Found {} UF2s (Phase 7)".format(len(fws)))
                except Exception:
                    _render("No /sd/firmwares/ directory")
            else:
                return choice
        elif k == "ENTER":
            choice = items[sel][2]
            if choice == "uf2_scan":
                try:
                    fws = [f for f in os.listdir("/sd/firmwares") if f.endswith(".uf2")]
                    _render("Found {} UF2s (Phase 7)".format(len(fws)))
                except Exception:
                    _render("No /sd/firmwares/ directory")
            else:
                return choice
        time.sleep_ms(30)


def _ensure_pinhos_path():
    if "/sd/pinhos" in sys.path:
        sys.path.remove("/sd/pinhos")
    sys.path.insert(0, "/sd/pinhos")


def _launch_recovery():
    _ensure_pinhos_path()
    try:
        import main as _pm
        _pm.enter_safe_recovery_mode(reason="User requested Recovery Mode", interactive=True)
    except Exception as e:
        _draw_splash("Recovery Mode (Serial COM4)", str(e)[:34])
        print("[PinhOS] Recovery fallback:", repr(e))


def _launch_pinhos():
    _ensure_pinhos_path()
    try:
        os.stat("/sd/pinhos/main.py")
    except Exception:
        _draw_splash("SD /sd/pinhos/main.py missing!", "COM4 Serial REPL Active")
        print("[PinhOS] /sd/pinhos/main.py not found; COM4 REPL active.")
        return

    gc.collect()
    import main as _pm
    _pm.start(skip_strike_increment=False, interactive=True)


def boot():
    kb = None
    try:
        import picocalc
        kb = getattr(picocalc, "keyboard", None)
    except Exception:
        kb = None

    _draw_splash("Booting PinhOS...", "[ESC/F1] Recovery  [F2] Boot Menu")

    # Wait 150ms for STM32 southbridge post-reset settle, then 1.5s hotkey window
    time.sleep_ms(150)
    choice = None
    for _ in range(50):
        k = _poll_hotkey(kb)
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

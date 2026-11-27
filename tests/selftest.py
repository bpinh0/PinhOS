# PinhOS Phase 1 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Automated On-Device Self-Test Gate (tests/selftest.py)
# Invoked via `.\picocalc.ps1 test` to verify:
# 1. Canonical Layout & version.json Manifest
# 2. HAL Init (Display, I2C Keyboard/Modifiers/Battery, SPI SD, Backlight, GenericSPI fallback)
# 3. Cooperative .swap/ R/W Roundtrip, Corruption Recovery & Core Helpers
# 4. Sandbox APP_META Static Inspection, Handle Leak Closure, Module Purge & SRAM Reclamation (< 2048 B)
# 5. 3-Strike Boot Guard & Safe Recovery Mode Trigger Logic
# 6-8. Input/Boot router, Unified Theme Engine, Dual-UI dirty redraw (Phase 2)
# 9. BusyBox Shell & Streaming File Commands (Phase 3)

import os
import sys
import gc
import json

for _p in (".", "/", "/sd/pinhos"):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

def _bp(*args):
    """Write test output via board.serial_print() (zero hardcoded pins in selftest.py)."""
    try:
        from boards import get_board
        b = get_board()
        if hasattr(b, "serial_print"):
            b.serial_print(*args)
            return
    except Exception:
        pass
    print(" ".join(str(a) for a in args))


def _clear_main_refs():
    try:
        import builtins as _bi
    except Exception:
        _bi = None
    if _bi is not None:
        for _k in (
            "recovery_status", "recovery_reset_strikes", "recovery_reset_config",
            "recovery_clear_swap", "recovery_reboot", "ui",
        ):
            try:
                if hasattr(_bi, _k):
                    delattr(_bi, _k)
            except Exception:
                pass
    for _mk in ("main", "_pinhos_main"):
        m = sys.modules.pop(_mk, None)
        if m is not None and hasattr(m, "runtime_state") and isinstance(m.runtime_state, dict):
            m.runtime_state.clear()


_KEEP_MODS = (
    "boards", "boards.base", "boards.picocalc", "core.config",
    "tests", "tests.selftest", "picocalc", "picocalcdisplay", "vtterminal",
)


def _purge_noncore():
    _clear_main_refs()
    for _m in list(sys.modules.keys()):
        if _m not in _KEEP_MODS and (
            _m.startswith("ui.") or _m.startswith("tools.") or _m.startswith("core.")
            or _m.startswith("net.") or _m.startswith("web") or _m.startswith("tests.selftest_")
            or _m in ("ui", "tools", "net", "uasyncio", "asyncio", "asyncio.core", "asyncio.stream", "asyncio.funcs", "asyncio.event", "asyncio.lock")
        ):
            sys.modules.pop(_m, None)
    gc.collect()
    gc.collect()


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_manifest_and_dirs(root="/sd/pinhos"):
    from core.config import ensure_canonical_dirs, load_version_manifest, CANONICAL_SUBDIRS

    dir_res = ensure_canonical_dirs(root=root)
    _assert(dir_res["ok"], "Failed to initialize canonical directories under " + root)

    for sub in CANONICAL_SUBDIRS:
        full = root.rstrip("/") + "/" + sub
        st = os.stat(full)
        _assert(bool(st[0] & 0x4000), "Missing canonical directory: " + full)

    manifest = load_version_manifest(root=root)
    _assert(manifest.get("version") == "1.0.0-alpha.5.1.2", "Expected version 1.0.0-alpha.5.1.2")
    _assert(manifest.get("arch") == "armv7emsp", "Expected target arch armv7emsp")
    _assert(isinstance(manifest.get("ota"), dict) and "channel" in manifest["ota"], "Missing OTA channel field")
    return "v{} ({}) +{} dirs".format(
        manifest["version"], manifest["arch"], len(CANONICAL_SUBDIRS)
    )


def test_hal_init(root="/sd/pinhos"):
    from boards import (
        get_board,
        create_board,
        CAP_DISPLAY,
        CAP_KEYBOARD,
        CAP_SDCARD,
        CAP_BATTERY,
        CAP_BACKLIGHT,
        MOD_CTRL,
        MOD_SHIFT,
    )

    board = get_board()
    _assert(board.initialized, "Primary board failed to initialize")
    _assert(board.display_width == 320 and board.display_height == 320, "Display dimensions must be 320x320")
    for cap in (CAP_DISPLAY, CAP_KEYBOARD, CAP_SDCARD, CAP_BATTERY, CAP_BACKLIGHT):
        _assert(board.has_capability(cap), "Missing required board capability flag: " + str(cap))

    # Display primitives & blit test
    board.fill(0)
    board.fill_rect(8, 8, 64, 32, 3)
    board.rect(4, 4, 312, 312, 15)
    board.hline(10, 50, 100, 10)
    board.vline(10, 50, 50, 10)
    board.line(10, 50, 60, 100, 14)
    board.pixel(160, 160, 15)
    board.text("PinhOS Phase 1 HAL Test", 20, 20, 15)
    blit_buf = bytearray(16 * 16)
    board.blit(blit_buf, 200, 200, 16, 16, fmt="GS4_HMSB")

    # Input queue & modifier decoding test
    board.clear_input()
    board.push_event({"type": "key", "key": "F1", "modifiers": 0})
    _assert(board.poll_key() == "F1", "Input queue failed to roundtrip key event")
    _assert(len(board._input_queue) == 0, "Input queue should be empty after pop")

    if hasattr(board, "_decode_raw_key"):
        k_up, _ = board._decode_raw_key(b"\x1b[A")
        _assert(k_up == "UP", "Failed VT100 UP arrow decode")
        k_ctrl, m_ctrl = board._decode_raw_key(b"\x03")
        _assert(k_ctrl == "C" and (m_ctrl & MOD_CTRL), "Failed Ctrl+C modifier decode")
        k_sh, m_sh = board._decode_raw_key(b"A")
        _assert(k_sh == "A" and (m_sh & MOD_SHIFT), "Failed Shift modifier decode")
        k_f6, m_f6 = board._decode_raw_key(b"\x86")
        _assert(k_f6 == "F6" and (m_f6 & MOD_SHIFT), "Failed STM32 Shift+F6 decode")
        k_f10, m_f10 = board._decode_raw_key(b"\x8a")
        _assert(k_f10 == "F10" and (m_f10 & MOD_SHIFT), "Failed STM32 Shift+F10 decode")

    # Battery telemetry check
    bat = board.get_battery()
    _assert(isinstance(bat, dict), "get_battery() must return a dict")
    _assert(0 <= int(bat.get("percent", -1)) <= 100, "Battery percent out of range 0..100")
    _assert(int(bat.get("voltage_mv", 0)) >= 2500, "Battery voltage_mv invalid")
    _assert(isinstance(bat.get("charging"), bool), "Battery charging flag must be bool")

    # Backlight PWM check
    orig_bl = board.get_backlight()
    board.set_backlight(75)
    _assert(board.get_backlight() == 75, "Backlight PWM getter/setter mismatch")
    board.set_backlight(orig_bl)

    # RTC check
    ts = board.get_timestamp_str()
    _assert(isinstance(ts, str) and len(ts) >= 8, "RTC timestamp invalid")

    # GenericSPIBoard fallback profile verification (virtual_only=True avoids touching
    # physical PicoCalc PSRAM/LCD GPIO pins during on-device self-test)
    gen_board = create_board("generic_spi", config={"virtual_only": True})
    _assert(gen_board.init(), "GenericSPIBoard failed to initialize")
    gen_board.fill(0)
    gen_board.rect(0, 0, 100, 100, 3)
    gen_board.text("Generic SPI OK", 10, 10, 15)
    gen_board.deinit()
    del gen_board
    sys.modules.pop("boards.generic_spi", None)
    gc.collect()
    board.ensure_serial_repl()

    # Verify zero hardcoded machine.Pin calls outside boards/
    for mod_rel in (
        "main.py",
        "core/config.py",
        "core/logger.py",
        "core/watchdog.py",
        "core/swap.py",
        "core/sandbox.py",
        "core/theme.py",
        "ui/fonts.py",
        "ui/widgets.py",
        "ui/gui.py",
        "ui/tui.py",
        "ui/engine.py",
        "ui/menu.py",
        "ui/desktop.py",
        "tools/shell.py",
        "tools/editor.py",
        "tools/files.py",
        "tools/net_tools.py",
        "tools/uart_term.py",
        "tools/sysmon.py",
        "web/server.py",
        "boards/base.py",
    ):
        p = root.rstrip("/") + "/" + mod_rel
        try:
            with open(p, "r") as f:
                for line in f:
                    _assert("machine.Pin(" not in line, "Hardcoded machine.Pin found in " + mod_rel)
        except OSError:
            pass

    return "{} (BAT {}% {}mV)".format(board.id, bat["percent"], bat["voltage_mv"])


def test_swap_and_core(root="/sd/pinhos"):
    from core.swap import SwapManager
    from core.config import ConfigManager
    from core.logger import Logger

    swap_dir = root.rstrip("/") + "/.swap"
    sm = SwapManager(swap_dir=swap_dir)
    sm.clear_all()

    # 1. Valid save & load roundtrip
    sample_state = {
        "cursor": [12, 34],
        "buffer": "PinhOS Phase 1 Swap Test",
        "baud": 115200,
        "flags": {"echo": True, "hex": False},
    }
    _assert(sm.save("selftest_app", sample_state), "swap.save() returned False")
    _assert(sm.exists("selftest_app"), "swap.exists() returned False after save")

    loaded = sm.load("selftest_app")
    _assert(loaded == sample_state, "swap.load() mismatch: " + repr(loaded))

    # 2. Corruption handling check (tampered payload / broken JSON)
    corrupt_path = sm._file_path("corrupt_app")
    with open(corrupt_path, "w") as f:
        f.write('{"magic":"PINHOS_SWAP_V1","app_id":"corrupt_app","checksum":123,"payload":"{bad_json"}')
    _assert(sm.load("corrupt_app") is None, "Corrupted swap file must return None")
    _assert(not sm.exists("corrupt_app"), "Corrupted swap file must be automatically deleted")

    # 3. Orphaned .tmp & stale pruning check
    tmp_orphan = swap_dir + "/orphan.swap.json.tmp"
    with open(tmp_orphan, "w") as f:
        f.write("partial_write")
    pruned = sm.prune_stale(max_age_s=86400, max_files=16)
    _assert(pruned >= 1, "prune_stale() failed to remove orphaned .tmp file")
    sm.delete("selftest_app")

    # 4. Config & Logger check
    cfg_path = root.rstrip("/") + "/logs/_selftest_cfg.json"
    cfg = ConfigManager(config_path=cfg_path)
    cfg.set("lcd_brightness", 77)
    cfg2 = ConfigManager(config_path=cfg_path)
    _assert(cfg2.get("lcd_brightness") == 77, "ConfigManager failed to persist setting")
    try:
        os.remove(cfg_path)
    except Exception:
        pass

    log = Logger(log_dir=root.rstrip("/") + "/logs")
    log.info("SELFTEST: swap and core helpers verified")
    _assert(len(log.get_recent(5)) >= 1, "Logger ring buffer empty")

    # 5. Breadcrumb & crash forensics roundtrip check (isolated temp log dir)
    bc_dir = root.rstrip("/") + "/logs/_selftest_bc"
    bc_log = Logger(log_dir=bc_dir)
    bc_log.set_breadcrumb("SIMULATED_FREEZE", "gate3")
    rep = bc_log.check_previous_crash()
    _assert(isinstance(rep, dict) and rep.get("op") == "SIMULATED_FREEZE", "Crash breadcrumb not detected")
    _assert(bc_log.check_previous_crash() is None, "Breadcrumb not cleared after crash report")
    crash_tail = bc_log.read_tail("crash", max_lines=10)
    _assert(any("SIMULATED_FREEZE" in ln for ln in crash_tail), "Crash report missing from crash.log tail")
    for fn in ("system.log", "crash.log", "breadcrumb.json"):
        try:
            os.remove(bc_dir + "/" + fn)
        except Exception:
            pass
    try:
        os.rmdir(bc_dir)
    except Exception:
        pass

    # 6. Two-Stage Soft Watchdog (Wait / Abort / timeout config, without arming silicon WDT)
    from core.watchdog import TwoStageWatchdog, SoftWatchdogAbort
    from boards import get_board as _gb
    _wb = _gb()
    swdt = TwoStageWatchdog(hw_timeout_ms=8000, soft_timeout_s=15, board=_wb, logger=None, arm_hw=False)
    _assert(swdt.get_soft_timeout_s() == 15, "Soft WDT initial timeout mismatch")
    swdt.set_soft_timeout_s(30)
    _assert(swdt.get_soft_timeout_s() == 30, "Soft WDT set_soft_timeout_s failed")
    swdt.pause()
    swdt.resume()
    _wb.clear_input()
    _wb.push_event({"type": "key", "key": "W", "modifiers": 0})
    _assert(swdt.prompt_not_responding(30) == "wait", "Soft WDT [W] Wait failed")
    _wb.clear_input()
    _wb.push_event({"type": "key", "key": "ESC", "modifiers": 0})
    aborted = False
    try:
        swdt.prompt_not_responding(30)
    except SoftWatchdogAbort:
        aborted = True
    _assert(aborted, "Soft WDT [ESC] Abort did not raise SoftWatchdogAbort")
    swdt.deinit()

    # 7. MemGuard: reclaim() unloads stale transient modules; ensure_heap() pre-flight passes
    from core.memutil import reclaim, ensure_heap
    sys.modules["ui._menu_net"] = sys
    sys.modules["ui._log_view"] = sys
    reclaim(1, None, keep=("tests.selftest",))
    _assert("ui._menu_net" not in sys.modules and "ui._log_view" not in sys.modules, "MemGuard reclaim() left stale modules")
    mg_free, mg_ok = ensure_heap(None, min_free=1024, min_blk=1024, keep=("tests.selftest",))
    _assert(mg_ok and mg_free > 1024, "MemGuard ensure_heap pre-flight failed")

    return "R/W + CRC + crash + SoftWDT + MemGuard OK"


def test_sandbox_isolation(root="/sd/pinhos"):
    if root and root not in sys.path:
        sys.path.insert(0, root)
    from core.sandbox import (
        SandboxRunner,
        SandboxMetaError,
        SandboxMemoryError,
        parse_app_meta,
        get_free_sram,
    )
    from core.swap import SwapManager
    from boards import get_board

    board = get_board()
    swap = SwapManager(swap_dir=root.rstrip("/") + "/.swap")
    runner = SandboxRunner(board=board, swap=swap)

    # 1. Verify parse_app_meta does NOT execute top-level app code
    trap_source = '''
APP_META = {
    "id": "trap_app",
    "name": "Trap App",
    "version": "1.0.0",
    "category": "Field Tools",
    "entry": "main",
    "min_sram": 16384,
    "ui_modes": ["native"],
}

raise RuntimeError("TOP_LEVEL_CODE_WAS_EXECUTED_DURING_INSPECTION")

def main(ctx):
    return "unreachable"
'''
    meta = parse_app_meta(trap_source)
    _assert(meta["id"] == "trap_app" and meta["min_sram"] == 16384, "Static APP_META parse failed")

    # 2. Verify min_sram gate blocks oversized apps before execution
    oom_source = '''
APP_META = {
    "id": "oom_app",
    "name": "Oversized App",
    "version": "1.0.0",
    "category": "System",
    "entry": "main",
    "min_sram": 99999999,
    "ui_modes": ["native"],
}
def main(ctx):
    return True
'''
    oom_caught = False
    try:
        runner.run_source(oom_source)
    except SandboxMemoryError:
        oom_caught = True
    _assert(oom_caught, "Sandbox failed to raise SandboxMemoryError when min_sram exceeds free SRAM")

    # 3. Create a temporary helper module on disk to verify sys.modules purging
    helper_mod_name = "_pinhos_sbx_helper_temp"
    helper_mod_path = root.rstrip("/") + "/" + helper_mod_name + ".py"
    leak_file_path = root.rstrip("/") + "/logs/_sbx_leak_test.txt"

    with open(helper_mod_path, "w") as f:
        f.write("HELPER_DATA = [x for x in range(64)]\ndef compute(v):\n    return v * 2\n")

    app_source = '''
APP_META = {{
    "id": "sbx_leak_test",
    "name": "Sandbox Leak Test",
    "version": "1.0.0",
    "category": "System",
    "entry": "main",
    "min_sram": 8192,
    "ui_modes": ["native"],
}}

def main(ctx):
    import {mod_name}
    # Intentionally leak an open file handle without closing it
    leaked_f = open("{leak_path}", "w")
    leaked_f.write("sandbox handle tracking test\\n")
    buf = bytearray(4096)
    buf[0] = {mod_name}.compute(21)
    ctx.save_state({{"ans": int(buf[0])}})
    if ctx.args.get("crash"):
        raise ValueError("Intentional sandbox crash test")
    return int(buf[0])
'''.format(mod_name=helper_mod_name, leak_path=leak_file_path)

    try:
        # Warm-up run so one-time interpreter/filesystem buffers stabilize
        res_warm = runner.run_source(app_source, args={"crash": False})
        _assert(res_warm["ok"] and res_warm["return_value"] == 42, "Sandbox normal run failed")
        _assert(res_warm["leaked_handles_closed"] >= 1, "Sandbox did not close leaked file handle")
        _assert(helper_mod_name not in sys.modules, "Imported module was not purged after normal exit")

        # Measure SRAM baseline before repeated normal + crashing runs
        gc.collect()
        gc.collect()
        sram_baseline = get_free_sram()

        # Run normal execution
        res_ok = runner.run_source(app_source, args={"crash": False})
        _assert(res_ok["ok"] and res_ok["return_value"] == 42, "Measured sandbox run failed")
        _assert(res_ok["leaked_handles_closed"] >= 1, "Leaked handle not closed on measured run")
        _assert(helper_mod_name not in sys.modules, "Module leaked into sys.modules")

        # Run crashing execution (uncaught exception inside main(ctx))
        res_crash = runner.run_source(app_source, args={"crash": True})
        _assert(not res_crash["ok"] and "Intentional sandbox crash" in str(res_crash["error"]), "Crash not caught")
        _assert(res_crash["leaked_handles_closed"] >= 1, "Leaked handle not closed on exception path")
        _assert(helper_mod_name not in sys.modules, "Module leaked into sys.modules on exception path")

        swap.delete("sbx_leak_test")
        gc.collect()
        gc.collect()
        sram_final = get_free_sram()
        residual_delta = max(0, sram_baseline - sram_final)

        _assert(
            residual_delta < 2048,
            "Sandbox SRAM leak delta {} bytes exceeds 2048-byte limit".format(residual_delta),
        )
    finally:
        for p in (helper_mod_path, leak_file_path):
            try:
                os.remove(p)
            except Exception:
                pass

    return "delta={}B (<2KB), handles+mods OK".format(residual_delta)


def test_boot_guard(root="/sd/pinhos"):
    had_main = "main" in sys.modules
    import main as pinhos_main

    test_state_path = root.rstrip("/") + "/logs/_selftest_boot_state.json"
    try:
        try:
            os.remove(test_state_path)
        except Exception:
            pass

        # Strike 1
        s1 = pinhos_main.record_boot_strike("fault_1", state_path=test_state_path)
        _assert(s1["boot_strikes"] == 1 and not s1["safe_mode"], "Strike 1 state invalid")

        # Strike 2
        s2 = pinhos_main.record_boot_strike("fault_2", state_path=test_state_path)
        _assert(s2["boot_strikes"] == 2 and not s2["safe_mode"], "Strike 2 state invalid")

        # Premature uptime (< 5000ms) must NOT clear strikes
        _assert(
            not pinhos_main.check_boot_stability(2500, state_path=test_state_path),
            "Boot strikes cleared prematurely before 5000ms",
        )
        _assert(
            pinhos_main.load_boot_state(state_path=test_state_path)["boot_strikes"] == 2,
            "Strike count mutated before 5s threshold",
        )

        # Strike 3 -> Safe Recovery Mode triggered on start()
        # (Note: start() increments strike 2 -> 3 at entry and immediately enters Safe Recovery Mode)
        boot_res = pinhos_main.start(state_path=test_state_path, wait_for_stability=False)
        _assert(
            isinstance(boot_res, dict) and boot_res.get("mode") == "SAFE_RECOVERY",
            "3rd strike failed to trigger SAFE_RECOVERY mode: " + repr(boot_res),
        )
        _assert(boot_res.get("strikes") == 3, "Expected strike count 3 in Safe Recovery Mode")

        # Verify recovery helper resets strikes cleanly
        reset_st = pinhos_main.recovery_reset_strikes(state_path=test_state_path)
        _assert(reset_st["boot_strikes"] == 0 and not reset_st["safe_mode"], "recovery_reset_strikes failed")

        # Verify >5s stability window clears strikes
        pinhos_main.record_boot_strike("normal_boot", state_path=test_state_path)
        _assert(
            pinhos_main.check_boot_stability(5050, state_path=test_state_path),
            "check_boot_stability(5050) failed to clear strikes",
        )
        final_st = pinhos_main.load_boot_state(state_path=test_state_path)
        _assert(final_st["boot_strikes"] == 0, "Strikes not 0 after >5s stability")
    finally:
        try:
            os.remove(test_state_path)
        except Exception:
            pass
        # Ensure real device boot_state is clean (0 strikes) and serial REPL stays bound
        pinhos_main.clear_boot_strikes()
        pinhos_main = None
        if not had_main:
            _clear_main_refs()
        gc.collect()
        try:
            from boards import get_board
            get_board().ensure_serial_repl()
        except Exception:
            pass

    return "3-strike Safe Mode & >5s reset OK"


def test_input_and_boot_router(root="/sd/pinhos"):
    """
    Gate 6: Verify non-blocking keyboard polling, PicoKeyboard.temp buffer integrity,
    and frozen pinhos_boot version.json + Boot Menu Up/Down + Ctrl+C stress stability.
    """
    import time
    from boards import get_board
    from core.config import load_version_manifest

    board = get_board()

    # 1. Verify PicoKeyboard scratch buffer integrity before/after clear_input + poll_key
    kb = getattr(board, "_kb", None)
    if kb is not None and hasattr(kb, "temp"):
        _assert(len(kb.temp) == 2, "PicoKeyboard.temp corrupted before poll: len={}".format(len(kb.temp)))

    board.clear_input()
    t0 = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
    for _ in range(5):
        board.poll_key()
    t1 = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
    elapsed_ms = time.ticks_diff(t1, t0) if hasattr(time, "ticks_diff") else (t1 - t0)
    _assert(elapsed_ms < 400, "board.poll_key() blocked ({}ms for 5 polls)".format(elapsed_ms))

    if kb is not None and hasattr(kb, "temp"):
        _assert(len(kb.temp) == 2, "PicoKeyboard.temp corrupted after poll: len={}".format(len(kb.temp)))

    # 2. Verify frozen pinhos_boot module (when running on RP2350 UF2 firmware)
    boot_note = "no frozen boot"
    try:
        import pinhos_boot
    except Exception:
        pinhos_boot = None

    if pinhos_boot is not None:
        manifest = load_version_manifest(root=root)
        pinhos_boot._cached_ver = None
        os_ver, fw_ver = pinhos_boot._load_version_info()
        _assert(
            os_ver == manifest.get("version"),
            "pinhos_boot version mismatch: {} != {}".format(os_ver, manifest.get("version")),
        )
        if manifest.get("firmware_version"):
            _assert(
                fw_ver == manifest.get("firmware_version"),
                "pinhos_boot fw mismatch: {} != {}".format(fw_ver, manifest.get("firmware_version")),
            )

        # Verify set_progress renders cleanly
        pinhos_boot._splash_drawn = False
        pinhos_boot.set_progress(50, "Gate 6 Self-Test...")
        pinhos_boot._splash_drawn = False

        # Stress-test Boot Menu: 20 rapid Up/Down events + Ctrl+C (0xA5 + 0x63)
        gc.collect()
        m0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144

        class _MockKB:
            def __init__(self):
                self.n = 0

            def keyEvent(self):
                self.n += 1
                if self.n <= 10:
                    return (1, 0xB6)  # DOWN
                if self.n <= 20:
                    return (1, 0xB5)  # UP
                if self.n == 21:
                    return (1, 0xA5)  # CTRL press
                if self.n == 22:
                    return (1, 0x63)  # 'c' press -> CTRL_C
                if self.n == 23:
                    return (3, 0xA5)  # CTRL release
                return None

        ctrl_c_caught = False
        try:
            pinhos_boot._show_boot_menu(_MockKB())
        except KeyboardInterrupt:
            ctrl_c_caught = True
        finally:
            pinhos_boot._ctrl_held = False
            pinhos_boot._splash_drawn = False

        _assert(ctrl_c_caught, "Boot Menu did not interrupt on Ctrl+C (0xA5 + 0x63)")
        gc.collect()
        m1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        delta = m0 - m1
        _assert(delta < 2048, "Boot Menu SRAM leak too high: {}B".format(delta))
        boot_note = "UF2 {} Ctrl+C OK ({}B)".format(fw_ver, delta)

    return "poll={}ms {}".format(elapsed_ms, boot_note)


def test_theme_engine(root="/sd/pinhos"):
    """
    Gate 7: Load and strictly validate all canonical JSON themes in /sd/pinhos/themes/
    (Schema v1 & Schema v2 including Obsidian Amber), verify deep-merged defaults,
    6x8 font resolution, pre-computed RGB565 ints, safe fallback, and hot-swap persistence.
    """
    from boards import get_board
    from core.config import ConfigManager
    from core.theme import (
        Theme,
        ThemeManager,
        CANONICAL_THEME_IDS,
        REQUIRED_TOKENS,
        load_theme_file,
    )

    board = get_board()
    themes_dir = root.rstrip("/") + "/themes"
    cfg_path = root.rstrip("/") + "/logs/_selftest_theme_cfg.json"

    try:
        try:
            os.remove(cfg_path)
        except Exception:
            pass

        cfg = ConfigManager(config_path=cfg_path)
        tm = ThemeManager(themes_dir=themes_dir, config=cfg, board=board)

        # 1. Strictly validate all canonical JSON themes (v1 + v2)
        validated = tm.validate_all()
        for tid in CANONICAL_THEME_IDS:
            _assert(tid in validated, "Missing canonical theme file: " + tid)
            ok, info = validated[tid]
            _assert(ok, "Theme '{}' failed validation: {}".format(tid, info))

            t = tm.load(tid, strict=True)
            _assert(len(t.lut) == 16, "Theme '{}' LUT must have 16 entries".format(tid))
            for tok in REQUIRED_TOKENS:
                idx = t.color(tok)
                hx = t.hex(tok)
                r565 = t.rgb565(tok)
                _assert(isinstance(idx, int) and 0 <= idx <= 15, "Invalid palette idx for {}.{}".format(tid, tok))
                _assert(isinstance(hx, str) and hx.startswith("#") and len(hx) == 7, "Invalid hex for {}.{}".format(tid, tok))
                _assert(isinstance(r565, int) and 0 <= r565 <= 0xFFFF, "Invalid rgb565 int for {}.{}".format(tid, tok))

        # Verify Obsidian Amber Schema v2 fields & Legacy flat theme deep-merge
        obs = tm.load("obsidian_amber", strict=True)
        _assert(obs.schema_version == 2 and obs.font == "bold" and obs.uppercase_headers, "Obsidian Amber v2 metadata mismatch")
        _assert(obs.style_token("bar_style") == "blocks" and obs.style_token("card_header") == "filled", "Obsidian Amber style mismatch")
        flat_t = Theme({"name": "Legacy Flat", "bg": "#08090C", "fg": "#FFB000", "accent": "#00E5FF"})
        _assert(flat_t.id == "legacy_flat" and len(flat_t.lut) == 16 and flat_t.font == "default", "Flat theme merge failed")

        # 2. Verify safe built-in fallback when file is missing
        fb = load_theme_file(themes_dir + "/_nonexistent_theme.json", strict=False)
        _assert(fb.id == "cyber_amber" and len(fb.lut) == 16, "Fallback theme failed")

        # 3. Verify runtime hot-swap + config.json persistence + listener callback
        events = []
        tm.register_listener(lambda th: events.append(th.id))
        tm.apply("obsidian_amber", persist=True)
        _assert(tm.active.id == "obsidian_amber" and board.get_font_name() == "bold", "apply('obsidian_amber') did not activate bold font")
        tm.apply("synthwave_pulse", persist=True)
        _assert(tm.active.id == "synthwave_pulse" and board.get_font_name() == "default", "apply('synthwave_pulse') did not restore default font")
        _assert("obsidian_amber" in events and "synthwave_pulse" in events, "Theme listener not notified on apply")

        cfg_reload = ConfigManager(config_path=cfg_path)
        _assert(cfg_reload.get("theme") == "synthwave_pulse", "Theme not persisted to config.json")

        # Restore default theme LUT cleanly
        tm.apply("cyber_amber", persist=False)
    finally:
        try:
            os.remove(cfg_path)
        except Exception:
            pass

    return "{}/{} JSON themes (v2+fonts) OK".format(len(CANONICAL_THEME_IDS), len(CANONICAL_THEME_IDS))


def test_dual_ui_engine(root="/sd/pinhos"):
    """
    Gate 8: Exercise Dual-UI Engine (GUI <-> TUI switching, theme cycling,
    dirty-row ListMenu navigation, all core widgets) and verify < 2048 B SRAM delta.
    """
    from boards import get_board
    from core.config import ConfigManager
    from core.theme import ThemeManager, CANONICAL_THEME_IDS
    from ui.engine import UIEngine
    from ui.widgets import StatusBar, FooterBar, Panel, ListMenu, ProgressBar, Dialog, TextView

    board = get_board()
    themes_dir = root.rstrip("/") + "/themes"
    cfg_path = root.rstrip("/") + "/logs/_selftest_ui_cfg.json"

    try:
        try:
            os.remove(cfg_path)
        except Exception:
            pass

        cfg = ConfigManager(config_path=cfg_path)
        tm = ThemeManager(themes_dir=themes_dir, config=cfg, board=board)
        ui = UIEngine(board=board, theme_manager=tm, config=cfg, mode="gui")

        sb = StatusBar(0, 0, 320, 20, title="PinhOS UI Gate", mode_label=ui.mode_badge, right_text="100%")
        pnl = Panel(4, 23, 312, 110, title="TELEMETRY", rows=[
            ("MODE :", "GUI", "accent"),
            ("THEME:", tm.active.name, "ok"),
            ("HEAP :", "OK", "info"),
        ])
        pbar = ProgressBar(8, 138, 304, 16, value=65, label="LOAD", color_token="ok")
        menu = ListMenu(4, 160, 312, 112, title="MENU", items=[
            {"label": "Item Alpha", "badge": "[1]"},
            {"label": "Item Beta", "badge": "[2]"},
            {"label": "Item Gamma", "badge": "[3]"},
            {"label": "Item Delta", "badge": "[4]"},
        ])
        fb = FooterBar(0, 276, 320, 44, status="Dual-UI Gate", status_kind="info", hints="TAB:Mode T:Theme")

        ui.add_widget(sb)
        ui.add_widget(pnl)
        ui.add_widget(pbar)
        ui.add_widget(menu)
        ui.add_widget(fb)
        ui.set_focus(menu)

        # Warm-up full render + one mode/theme switch so caches stabilize
        ui.render(force=True)
        ui.toggle_mode(persist=True)
        ui.render(force=False)
        ui.toggle_mode(persist=True)
        ui.render(force=False)

        # Also exercise Dialog and TextView widgets cleanly
        tv = TextView(8, 24, 304, 120, title="LOG", lines=["Line 1", "Line 2", "Line 3"])
        tv.draw(ui.backend, ui.theme, force=True)
        dlg = Dialog(30, 80, 260, 120, title="DIALOG", lines=["Dual-UI OK"], footer="[ENT]")
        dlg.draw(ui.backend, ui.theme, force=True)
        del tv, dlg

        # Baseline SRAM measurement BEFORE stress cycle
        gc.collect()
        gc.collect()
        m0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144

        # 1. Verify dirty-row partial redraw on ListMenu Up/Down navigation (20 steps)
        ui.render(force=True)
        for step in range(20):
            key = "DOWN" if step < 10 else "UP"
            res = ui.handle_key(key, allow_hotkeys=False)
            _assert(res == "handled", "ListMenu did not handle key " + key)
            drawn = ui.render(force=False)
            _assert(not ui.last_render_full, "ListMenu navigation triggered unexpected full-screen clear")
            _assert(drawn == 1, "Expected exactly 1 dirty widget on menu move, got {}".format(drawn))
            _assert(not menu.last_full_redraw, "ListMenu did full redraw instead of dirty-row redraw")
            _assert(menu.last_redraw_rows == 2, "Expected 2 dirty rows on move, got {}".format(menu.last_redraw_rows))

        # 2. Switch GUI <-> TUI modes & cycle all 4 themes
        for _ in range(2):
            new_mode = ui.toggle_mode(persist=True)
            sb.update(mode_label=ui.mode_badge)
            ui.render(force=False)
            _assert(ui.last_render_full, "Mode switch must trigger full clear redraw")
            _assert(cfg.get("ui_mode") == new_mode, "UI mode not persisted to config.json")

            for _t in range(len(CANONICAL_THEME_IDS)):
                ui.cycle_theme(step=1, persist=True)
                pnl.set_rows([
                    ("MODE :", ui.mode_badge, "accent"),
                    ("THEME:", ui.theme.name, "ok"),
                    ("HEAP :", "OK", "info"),
                ])
                ui.render(force=False)

        # Clean up & measure SRAM delta
        ui.set_mode("gui", persist=False)
        tm.apply("cyber_amber", persist=False)
        ui.deinit()
        del ui, tm, cfg, sb, pnl, pbar, menu, fb
        gc.collect()
        gc.collect()
        m1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        delta = max(0, m0 - m1)
        _assert(delta < 2048, "Dual-UI mode/theme switch SRAM delta {}B >= 2048B".format(delta))
    finally:
        try:
            os.remove(cfg_path)
        except Exception:
            pass

    return "GUI<->TUI + 2-row dirty (d={}B)".format(delta)


def test_busybox_shell(root="/sd/pinhos"):
    _purge_noncore()
    import tests.selftest_p3 as _p3
    try:
        return _p3.test_busybox_shell(root=root)
    finally:
        _p3 = None
        _purge_noncore()


def test_phase3_field_tools(root="/sd/pinhos"):
    _purge_noncore()
    import tests.selftest_p3 as _p3
    try:
        return _p3.test_phase3_field_tools(root=root)
    finally:
        _p3 = None
        _purge_noncore()


def test_desktop_home(root="/sd/pinhos"):
    _purge_noncore()
    import tests.selftest_p3 as _p3
    try:
        return _p3.test_desktop_home(root=root)
    finally:
        _p3 = None
        _purge_noncore()


def test_webportal_loopback(root="/sd/pinhos"):
    _purge_noncore()
    import tests.selftest_p4 as _p4
    try:
        return _p4.test_webportal_loopback(root=root)
    finally:
        _p4 = None
        _purge_noncore()


def run_all(root="/sd/pinhos", interactive_wait=False):
    from boards import get_board

    board = get_board()
    board.ensure_serial_repl()

    suites = [
        ("1. Manifest & Canonical Layout", test_manifest_and_dirs),
        ("2. Board HAL & Peripherals", test_hal_init),
        ("3. Swap Manager & Core Helpers", test_swap_and_core),
        ("4. Sandbox Isolation & SRAM Gate", test_sandbox_isolation),
        ("5. 3-Strike Boot Guard & Recovery", test_boot_guard),
        ("6. Input & Boot Router Integrity", test_input_and_boot_router),
        ("7. Unified Theme Engine (v2 JSON)", test_theme_engine),
        ("8. Dual-UI Dirty-Redraw & SRAM", test_dual_ui_engine),
        ("9. BusyBox Shell & Streaming FS", test_busybox_shell),
        ("10. Field Tools & Sandbox Meta", test_phase3_field_tools),
        ("11. Desktop Home & Quick Notes", test_desktop_home),
        ("12. WebPortal Loopback & SRAM", test_webportal_loopback),
    ]

    _bp("=== PinhOS v1.0.0-alpha.5.1.2 Phase 1+2+3.1+4 Self-Test Suite ===")
    passed = 0
    results = []

    def _draw_progress(idx, total_n, cur_lbl, done_rows):
        try:
            board.fill(0)
            board.fill_rect(0, 0, 320, 22, 3)
            board.text("PINHOS SELF-TEST [{}/{}]".format(idx, total_n), 12, 7, 0)
            board.text("Running: " + str(cur_lbl)[:38], 8, 28, 14)
            board.rect(8, 42, 304, 12, 7)
            fw = (300 * max(0, idx - 1)) // max(1, total_n)
            if fw > 0:
                board.fill_rect(10, 44, fw, 8, 10)
            ry = 62
            for r_lbl, r_ok, _r_det in done_rows[-12:]:
                board.text(("PASS " if r_ok else "FAIL ") + str(r_lbl)[:42], 8, ry, 10 if r_ok else 9)
                ry += 18
            board.show()
        except Exception:
            pass

    try:
        total_n = len(suites)
        for idx, (label, fn) in enumerate(suites, 1):
            try:
                _w = sys.modules.get("__pinhos_wdt__")
                if _w is not None:
                    _w.feed()
            except Exception:
                pass
            _draw_progress(idx, total_n, label, results)
            gc.collect()
            try:
                detail = fn(root=root)
                passed += 1
                results.append((label, True, detail))
                board.ensure_serial_repl()
                _bp("[PASS] {} -> {}".format(label, detail))
            except Exception as exc:
                results.append((label, False, repr(exc)))
                board.ensure_serial_repl()
                _bp("[FAIL] {} -> {}".format(label, repr(exc)))

        total = len(suites)
        all_ok = (passed == total)

        # Render final summary onto the PicoCalc display
        try:
            board.ensure_serial_repl()
            board.recover_refresh()
            board.fill(0)
            hdr_col = 10 if all_ok else 9
            board.fill_rect(0, 0, 320, 22, hdr_col)
            board.text(
                "SELFTEST: {} ({}/{})".format("ALL PASSED" if all_ok else "FAILED", passed, total),
                12,
                7,
                0,
            )
            y = 24
            for label, ok, detail in results:
                tag = "[PASS]" if ok else "[FAIL]"
                col = 10 if ok else 9
                board.text("{} {}".format(tag, label[:44]), 4, y, col)
                board.text(" " + str(detail)[:50], 4, y + 9, 15)
                y += 20
            free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
            board.fill_rect(0, 272, 320, 22, 8)
            if interactive_wait:
                board.text("ENT/SPC:Dashboard  R:Re-Test  ESC:Back", 8, 279, 15)
            else:
                board.text("COM4 Test Done | Run upload_and_start", 12, 279, 15)
            board.fill_rect(0, 294, 320, 26, 3)
            board.text("SRAM FREE: {} KB | STRIKES: 0/3".format(free_kb), 16, 303, 0)
            board.show()
        except Exception:
            pass

        status_tag = "PASS" if all_ok else "FAIL"
        _bp("<<PINHOS:SELFTEST:{}:{}/{}>>".format(status_tag, passed, total))

        if interactive_wait and board is not None:
            import time
            board.clear_input()
            try:
                poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
                while True:
                    k = poll_fn() if poll_fn else None
                    if k:
                        ku = str(k).upper()
                        if ku in ("R", "F2"):
                            board.beep(1400, 15)
                            return run_all(root=root, interactive_wait=True)
                        if ku in ("ENTER", "SPACE", " ", "ESC", "BACK", "BACKSPACE", "Q"):
                            board.beep(1100, 12)
                            break
                    if hasattr(time, "sleep_ms"):
                        time.sleep_ms(30)
                    else:
                        time.sleep(0.03)
            except KeyboardInterrupt:
                pass

        return {"ok": all_ok, "passed": passed, "total": total, "results": results}
    finally:
        # Guarantee COM4 (UART0 GP0/GP1) remains attached to os.dupterm(..., 0) on exit
        try:
            board.ensure_serial_repl()
        except Exception:
            pass


if __name__ == "__main__":
    res = run_all()
    if not res["ok"]:
        sys.exit(1)

# PinhOS Phase 3 — System Monitor & Settings (tools/sysmon.py)
# Live SRAM sparkline (primitive-drawn), GC cycle counter, RP2350 CPU freq & die temp,
# 1 KB chunked SD R/W speed benchmark, LCD/KB backlight sliders, UI mode & theme switcher.
# Zero full-screen framebuffers; zero hardcoded GPIO pins.

APP_META = {
    "id": "sysmon",
    "name": "System Monitor",
    "version": "1.0.0",
    "category": "System",
    "description": "Live SRAM sparkline, CPU/temp, SD R/W benchmark & backlight/theme settings",
    "entry": "main",
    "min_sram": 32768,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}

import gc
import os
import time

BENCH_PATH = "/sd/pinhos/logs/_sd_bench.tmp"


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else (a - b)


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def run_sd_benchmark(kb_count=32):
    """Stream kb_count x 1 KB write + read benchmark to SD, then clean up."""
    buf = bytes([0x55]) * 1024
    try:
        t0 = _ticks_ms()
        with open(BENCH_PATH, "wb") as f:
            for _ in range(kb_count):
                f.write(buf)
        w_ms = max(1, _ticks_diff(_ticks_ms(), t0))

        t1 = _ticks_ms()
        with open(BENCH_PATH, "rb") as f:
            while f.read(1024):
                pass
        r_ms = max(1, _ticks_diff(_ticks_ms(), t1))
        return {
            "ok": True,
            "write_kbps": (kb_count * 1000) // w_ms,
            "read_kbps": (kb_count * 1000) // r_ms,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "write_kbps": 0, "read_kbps": 0}
    finally:
        try:
            os.remove(BENCH_PATH)
        except OSError:
            pass
        gc.collect()


def _draw_sparkline(board, theme, x, y, w, h, samples):
    """Draw a compact SRAM usage sparkline using board primitives only."""
    c_surf = theme.color("surface")
    c_bdr = theme.color("border")
    c_acc = theme.color("accent")
    c_ok = theme.color("ok")
    c_txt = theme.color("text_muted")

    board.fill_rect(x, y, w, h, c_surf)
    board.rect(x, y, w, h, c_bdr)
    board.text("SRAM FREE SPARKLINE (KB)", x + 6, y + 4, c_acc)
    if not samples:
        return
    plot_y = y + 16
    plot_h = max(8, h - 20)
    bar_w = max(2, (w - 12) // max(1, len(samples)))
    lo = min(samples)
    hi = max(samples)
    span = max(16, hi - lo)
    for i, val in enumerate(samples):
        bx = x + 6 + i * bar_w
        if bx + bar_w > x + w - 4:
            break
        bh = max(2, ((val - lo) * plot_h) // span)
        board.fill_rect(bx, plot_y + plot_h - bh, max(1, bar_w - 1), bh, c_ok)
    board.text("{}..{}K".format(lo, hi), x + w - 66, y + 4, c_txt)


def main(ctx):
    board, ui = ctx.board, ctx.ui
    if board is None or ui is None:
        return {"error": "no board/ui"}

    from ui.widgets import StatusBar, Panel, ProgressBar, FooterBar

    gc_cycles = 0
    samples = []
    bench_str = "Press [B] to run 32KB test"
    hints = "L/R:LCD +/-:KB G:GC B:Bench M:Mode T:Thm ESC"

    sb = StatusBar(0, 0, 320, 20, title="SysMon & Cfg", mode_label=ui.mode_badge)
    pnl = Panel(4, 23, 312, 134, title="RP2350 TELEMETRY", label_width=98)
    pbar = ProgressBar(4, 232, 312, 18, value=board.get_backlight(), label="LCD BL", color_token="accent")
    kbar = ProgressBar(4, 253, 312, 18, value=board.get_kb_backlight(), label="KB  BL", color_token="info")
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=hints)

    ui.clear_widgets()
    ui.add_widget(sb); ui.add_widget(pnl); ui.add_widget(pbar); ui.add_widget(kbar); ui.add_widget(fb)

    def refresh(status_msg="Live monitor active", status_kind="ok", force=False):
        free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        used_b = gc.mem_alloc() if hasattr(gc, "mem_alloc") else 65536
        fk, uk = free_b // 1024, used_b // 1024
        bk = 0
        try:
            from core.memutil import largest_free
            bk = largest_free() // 1024
        except Exception:
            pass
        samples.append(fk)
        if len(samples) > 48:
            samples.pop(0)
        try:
            import machine
            mhz = machine.freq() // 1000000
        except Exception:
            mhz = 150
        bat = board.get_battery()
        devs = board.i2c_scan() if hasattr(board, "i2c_scan") else []
        rows = [
            ("SRAM FREE:", "{}K (u:{}K blk:{}K)".format(fk, uk, bk), "ok" if (fk > 64 and bk >= 16) else "warn"),
            ("GC CYCLES:", "{} runs".format(gc_cycles), "info"),
            ("CPU / DIE:", "{}MHz | {}C".format(mhz, board.get_cpu_temp_c()), "text"),
            ("BATTERY  :", "{}% ({}mV{})".format(bat["percent"], bat["voltage_mv"], " CHG" if bat["charging"] else ""), "text"),
            ("I2C / RTC:", "{} dev | {}".format(len(devs), board.get_timestamp_str(True)), "text"),
            ("UI / THM :", "{} | {}".format(ui.mode_badge, ui.theme.name[:18]), "accent"),
            ("SD BENCH :", bench_str, "info"),
        ]
        sb.update(mode_label=ui.mode_badge, right_text="{}%".format(bat["percent"]))
        pnl.set_rows(rows)
        pbar.set_value(board.get_backlight(), label="LCD BL")
        kbar.set_value(board.get_kb_backlight(), label="KB  BL")
        fb.update(status=status_msg, status_kind=status_kind, hints=hints)
        ui.render(force=force)
        _draw_sparkline(board, ui.theme, 4, 160, 312, 68, samples)
        board.show()

    refresh("System Monitor Ready", "ok", force=True)
    board.clear_input()

    try:
        ticks = 0
        while True:
            k = board.poll_key()
            if k is not None:
                ticks = 0
                ku = k.upper()
                try:
                    from boards.base import MOD_CTRL
                    ctrl = bool(board.get_modifiers() & MOD_CTRL)
                except Exception:
                    ctrl = False
                if (ctrl and ku == "P") or getattr(board, "pending_screenshot", None):
                    from ui.widgets import show_screenshot_toast
                    _, smsg = show_screenshot_toast(board, ui, fb)
                    refresh(smsg or "Screenshot saved", "ok", force=True)
                    continue
                if ku in ("ESC", "Q"):
                    break
                elif ku == "LEFT":
                    nv = max(10, board.get_backlight() - 10)
                    board.set_backlight(nv)
                    if ctx.config:
                        ctx.config.set("lcd_brightness", nv, save_now=True)
                    refresh("LCD Backlight: {}%".format(nv), "ok")
                elif ku == "RIGHT":
                    nv = min(100, board.get_backlight() + 10)
                    board.set_backlight(nv)
                    if ctx.config:
                        ctx.config.set("lcd_brightness", nv, save_now=True)
                    refresh("LCD Backlight: {}%".format(nv), "ok")
                elif ku in ("-", "_"):
                    nv = max(0, board.get_kb_backlight() - 10)
                    board.set_kb_backlight(nv)
                    if ctx.config:
                        ctx.config.set("kb_brightness", nv, save_now=True)
                    refresh("KB Backlight: {}%".format(nv), "ok")
                elif ku in ("+", "="):
                    nv = min(100, board.get_kb_backlight() + 10)
                    board.set_kb_backlight(nv)
                    if ctx.config:
                        ctx.config.set("kb_brightness", nv, save_now=True)
                    refresh("KB Backlight: {}%".format(nv), "ok")
                elif ku == "G":
                    b0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
                    gc.collect()
                    gc_cycles += 1
                    b1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
                    refresh("GC reclaimed {} B".format(max(0, b1 - b0)), "ok")
                elif ku == "B":
                    refresh("Benchmarking SD (32KB)...", "warn")
                    res = run_sd_benchmark(32)
                    if res["ok"]:
                        bench_str = "W:{}K/s R:{}K/s".format(res["write_kbps"], res["read_kbps"])
                        refresh("SD Bench: " + bench_str, "ok")
                    else:
                        bench_str = "Err: " + res.get("error", "?")[:18]
                        refresh("SD Bench failed", "err")
                elif ku in ("M", "TAB"):
                    ui.toggle_mode(persist=True)
                    refresh("Switched to {} Mode".format(ui.mode_badge), "ok", force=True)
                elif ku == "T":
                    nt = ui.cycle_theme(step=1, persist=True)
                    refresh("Theme: " + nt.name, "ok", force=True)
            else:
                ticks += 1
                if ticks >= 33:
                    ticks = 0
                    refresh("Live monitor active", "info")
                _sleep_ms(30)
        return {"gc_cycles": gc_cycles, "samples": len(samples)}
    finally:
        ui.clear_widgets()
        gc.collect()

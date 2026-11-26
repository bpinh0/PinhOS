# PinhOS Phase 3 — BusyBox System, Hardware & Inspection Commands (tools/_shell_cmds.py)
# Loaded by tools/shell.py (and purged cleanly by SandboxRunner on exit).
# Zero hardcoded GPIO pins; all hardware telemetry routes through board HAL.

import os
import gc
import sys
import time


def _hsize(n):
    if n < 1024:
        return "{}B".format(n)
    for u in ("K", "M", "G"):
        n = n / 1024.0
        if n < 1024 or u == "G":
            return "{:.1f}{}".format(n, u) if n < 10 else "{}{}".format(int(n), u)
    return str(n)


def _bat_line(b):
    mv = int(b.get("voltage_mv", 0))
    return "{}% {}.{:02d}V {}".format(
        b.get("percent", 0), mv // 1000, (mv % 1000) // 10, "CHG" if b.get("charging") else "BAT")


def _manifest():
    try:
        from core.config import load_version_manifest
        return load_version_manifest()
    except Exception:
        return {}


def cmd_free(sh, a, inp):
    fl, _ = sh.opts(a, "", "free")
    b0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
    gc.collect()
    after = gc.mem_free() if hasattr(gc, "mem_free") else 262144
    used = gc.mem_alloc() if hasattr(gc, "mem_alloc") else 65536
    tot = after + used
    div, unit = (1024, "KB") if "k" in fl else (1, "B")
    return [
        ("m", "{:<5} {:>10} {:>10} {:>10}".format(unit, "total", "used", "free")),
        "Mem:  {:>10} {:>10} {:>10}".format(tot // div, used // div, after // div),
        ("o", "gc: +{}B | {}% used".format(max(0, after - b0), (used * 100) // max(1, tot))),
    ]


def cmd_ps(sh, a, inp):
    gc.collect()
    u = (gc.mem_alloc() // 1024) if hasattr(gc, "mem_alloc") else 64
    f = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
    return [
        ("m", " PID NAME            CORE STATE"),
        "   1 pinhos.main        0 run",
        "   2 {:<15} 0 run (sandbox)".format(sh.app_id[:15]),
        "   - display-refresh    1 run (C)",
        "heap {}K used / {}K free | {} mods".format(u, f, len(sys.modules)),
    ]


def cmd_df(sh, a, inp):
    yield ("m", "{:<8} {:>5} {:>5} {:>5} {:>4} {}".format("FS", "Size", "Used", "Avail", "Use%", "Mount"))
    for mp, lbl in (("/", "flash"), ("/sd", "sdcard")):
        try:
            st = os.statvfs(mp)
        except OSError:
            yield ("w", "{:<8} (unmounted)".format(lbl))
            continue
        bs = st[1] or st[0]
        tot, av = bs * st[2], bs * st[3]
        used = tot - av
        pct = (used * 100) // tot if tot else 0
        yield "{:<8} {:>5} {:>5} {:>5} {:>3}% {}".format(lbl, _hsize(tot), _hsize(used), _hsize(av), pct, mp)


def cmd_uptime(sh, a, inp):
    ms = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
    d, r = divmod(ms // 1000, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    clk = sh.board.get_timestamp_str(True) if sh.board else "--:--:--"
    fk = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
    return ("{} up {}d {:02d}:{:02d}:{:02d} | {}K free".format(clk, d, h, m, s, fk),)


def cmd_dmesg(sh, a, inp):
    fl, pos = sh.opts(a, "n", "dmesg")
    if "w" in fl or (pos and pos[0] == "wdt"):
        kind = "wdt"
    elif "c" in fl or (pos and pos[0] == "crash"):
        kind = "crash"
    else:
        kind = "system"
    lines = sh.read_tail(sh.log_path(kind), sh.int_opt(fl, "n", 20, "dmesg"))
    if not lines:
        return [("m", "(no entries in {}.log)".format(kind))]
    return [("e" if ("[ERROR]" in s or "[CRASH]" in s) else ("w" if ("[WARN]" in s or "[WDT" in s) else " "), s) for s in lines]


def cmd_uname(sh, a, inp):
    m = _manifest()
    if a and a[0] == "-a":
        u = os.uname()
        return ["PinhOS {} {} {} uf2 {} | {} {}".format(
            m.get("version", "?"), m.get("arch", "?"), m.get("mcu", "?"),
            m.get("firmware_version", "?"), u[0], u[2])]
    return ("PinhOS",)


def cmd_ver(sh, a, inp):
    m = _manifest()
    u = os.uname()
    return [
        ("c", "PinhOS {} ({})".format(m.get("version", "?"), m.get("arch", "?"))),
        "Phase  : {} '{}'".format(m.get("phase", "?"), m.get("codename", "?")),
        "UF2 fw : {}".format(m.get("firmware_version", "?")),
        "Python : MicroPython {}".format(u[2]),
        "Board  : {}".format(sh.board.name if sh.board else "?"),
    ]


def cmd_bat(sh, a, inp):
    if sh.board is None:
        raise sh.Error("bat: no board HAL")
    return ("Battery: " + _bat_line(sh.board.get_battery()),)


def _set_lvl(sh, cmd, a, getter, setter, cfg_key, floor):
    if sh.board is None:
        raise sh.Error(cmd + ": no board HAL")
    cur = getter()
    if not a:
        return ("{}: {}%".format(cmd, cur),)
    s = a[0]
    try:
        val = cur + int(s) if (s[0] in "+-" and len(s) > 1) else int(s)
    except ValueError:
        raise sh.Error(cmd + ": 0-100, +N or -N")
    val = max(0, min(100, val))
    setter(val)
    note = ""
    if sh.config is not None and val >= floor:
        try:
            sh.config.set(cfg_key, val, save_now=True)
            note = " (saved)"
        except Exception:
            pass
    return ("{}: {}%{}".format(cmd, val, note),)


def cmd_bl(sh, a, inp):
    b = sh.board
    if b and not a:
        return ("bl: LCD {}%  KB {}%".format(b.get_backlight(), b.get_kb_backlight()),)
    return _set_lvl(sh, "bl", a, b.get_backlight if b else None, b.set_backlight if b else None, "lcd_brightness", 10)


def cmd_kbl(sh, a, inp):
    b = sh.board
    return _set_lvl(sh, "kbl", a, b.get_kb_backlight if b else None, b.set_kb_backlight if b else None, "kb_brightness", 0)


def cmd_theme(sh, a, inp):
    tm = sh.theme_mgr
    if tm is None:
        raise sh.Error("theme: unavailable")
    ids = tm.list_themes()
    if not a or a[0] == "list":
        act = tm.active.id
        return [("c", "* " + t) if t == act else "  " + t for t in ids]
    if a[0] == "next":
        return ("theme: " + tm.cycle(step=1, persist=True).id,)
    tid = tm._normalize_id(a[0])
    if tid not in ids:
        raise sh.Error("theme: unknown " + a[0])
    return ("theme: " + tm.apply(tid, persist=True).id,)


def cmd_mode(sh, a, inp):
    if sh.ui is None:
        raise sh.Error("mode: no UI")
    if not a:
        return ("mode: " + sh.ui.mode,)
    arg = a[0].lower()
    if arg in ("toggle", "next"):
        sh.ui.toggle_mode(persist=True)
    elif arg in ("gui", "tui"):
        sh.ui.set_mode(arg, persist=True)
    else:
        raise sh.Error("mode: gui|tui|toggle")
    return ("mode: " + sh.ui.mode,)


def cmd_date(sh, a, inp):
    if sh.board:
        return (sh.board.get_timestamp_str(),)
    t = time.localtime()
    return ("{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5]),)


def cmd_reboot(sh, a, inp):
    try:
        from core.config import save_rtc_state
        save_rtc_state(sh.board)
    except Exception:
        pass
    if sh.logger:
        try:
            sh.logger.info("SHELL: reboot")
            sh.logger.clear_breadcrumb("CLEAN_EXIT")
        except Exception:
            pass
    sh.out("Rebooting...", "w")
    if "flush" in sh.handlers:
        sh.handlers["flush"]()
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(200)
    import machine
    machine.soft_reset() if (a and a[0] == "-s") else machine.reset()


def cmd_hwinfo(sh, a, inp):
    b = sh.board
    if b is None:
        raise sh.Error("hwinfo: no board HAL")
    out = [("c", "{} [{}]".format(b.name[:40], b.id))]
    out.append("Display: {}x{} LCD:{}% KB:{}%".format(
        b.display_width, b.display_height, b.get_backlight(), b.get_kb_backlight()))
    try:
        import machine
        out.append("CPU    : {}MHz  die {}C".format(machine.freq() // 1000000, b.get_cpu_temp_c()))
    except Exception:
        out.append("CPU    : die {}C".format(b.get_cpu_temp_c()))
    out.append("RTC    : " + b.get_timestamp_str())
    out.append("Battery: " + _bat_line(b.get_battery()))
    sd = b.get_sd_stats()
    out.append("SD     : {} free / {}".format(_hsize(sd["free_kb"] * 1024), _hsize(sd["total_kb"] * 1024)) if sd.get("mounted") else "SD     : unmounted")
    devs = b.i2c_scan() if hasattr(b, "i2c_scan") else []
    out.append("I2C    : {} dev(s) {}".format(len(devs), " ".join(["0x{:02x}".format(d) for d in devs])))
    gc.collect()
    out.append("Heap   : {}K free".format((gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256))
    return out


def cmd_i2cscan(sh, a, inp):
    b = sh.board
    if b is None:
        raise sh.Error("i2cscan: no board HAL")
    found = b.i2c_scan() if hasattr(b, "i2c_scan") else []
    known = b.get_i2c_known() if hasattr(b, "get_i2c_known") else {}
    yield ("m", "   " + "".join(["{:>3x}".format(c) for c in range(16)]))
    for row in range(8):
        cells = []
        for col in range(16):
            addr = row * 16 + col
            cells.append("   " if (addr < 3 or addr > 0x77) else (" {:02x}".format(addr) if addr in found else " --"))
        yield "{:02x}:".format(row * 16) + "".join(cells)
    for addr in found:
        yield ("o", "0x{:02x} {}".format(addr, known.get(addr, "device")))
    if not found:
        yield ("w", "no I2C devices responded")


def cmd_com4(sh, a, inp):
    try:
        import machine
        u = machine.UART(0, 115200, rxbuf=4096)
        os.dupterm(u, 0)
        if sh.board is not None:
            sh.board._uart = u
    except Exception as e:
        raise sh.Error("com4: " + str(e))
    try:
        m = sys.modules.get("main")
        if m and isinstance(getattr(m, "runtime_state", None), dict):
            m.runtime_state["serial_link"] = True
    except Exception:
        pass
    return [("o", "COM4 UART0 115200 dupterm rebound + LNK ON")]


SYS_COMMANDS = {
    "free": cmd_free, "ps": cmd_ps, "df": cmd_df, "uptime": cmd_uptime,
    "dmesg": cmd_dmesg, "log": cmd_dmesg, "uname": cmd_uname, "ver": cmd_ver,
    "bat": cmd_bat, "bl": cmd_bl, "kbl": cmd_kbl, "theme": cmd_theme,
    "mode": cmd_mode, "date": cmd_date, "reboot": cmd_reboot,
    "hwinfo": cmd_hwinfo, "i2cscan": cmd_i2cscan, "com4": cmd_com4,
}

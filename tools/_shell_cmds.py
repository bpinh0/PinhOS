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


# --- Core FS Commands (pre-compiled .mpy to avoid on-device AST compile spikes) ---

def _ls_gen(sh, targets, lng, allf):
    for t in targets:
        p = sh.path(t); st = sh.stat_of(p)
        if st is None:
            raise sh.Error("ls: {}: No such file".format(t))
        if not (st[0] & 0x4000):
            yield ("- {:>6} {}".format(_hsize(st[6]), t) if lng else t); continue
        ents = sorted([(e[0], e[1] == 0x4000) for e in os.ilistdir(p) if allf or e[0][:1] != "."])
        if lng:
            for nm, isd in ents:
                s2 = sh.stat_of(sh.join(p, nm))
                if s2:
                    yield ("c" if isd else " ", "{} {:>6} {}{}".format("d" if isd else "-", _hsize(s2[6]), nm, "/" if isd else ""))
        else:
            for r in sh.format_columns([nm + "/" if isd else nm for nm, isd in ents]):
                yield r
        if not ents:
            yield ("m", "(empty)")


def cmd_ls(sh, a, inp):
    fl, pos = sh.opts(a, "", "ls")
    return _ls_gen(sh, pos or ["."], "l" in fl, "a" in fl)


def cmd_cd(sh, a, inp):
    t = sh.oldpwd if (a and a[0] == "-") else (a[0] if a else sh.HOME)
    p = sh.path(t)
    if not sh.is_dir(p):
        raise sh.Error("cd: {}: Not a directory".format(t))
    sh.oldpwd, sh.cwd = sh.cwd, p


def _srcs(sh, cmd, files, inp):
    if files:
        for f in files:
            yield f, sh.iter_lines(sh.need_file(cmd, f), sh.tick)
    elif inp is not None:
        yield "(stdin)", inp
    else:
        raise sh.Error(cmd + ": missing file")


def cmd_cat(sh, a, inp):
    fl, pos = sh.opts(a, "", "cat"); num = "n" in fl
    def _g():
        n = 0
        for _, it in _srcs(sh, "cat", pos, inp):
            for ln in it:
                n += 1; yield "{:>5} {}".format(n, ln) if num else ln
    return _g()


def cmd_head(sh, a, inp):
    fl, pos = sh.opts(a, "n", "head"); n = sh.int_opt(fl, "n", 10, "head")
    def _g():
        for _, it in _srcs(sh, "head", pos, inp):
            c = 0
            for ln in it:
                if c >= n:
                    break
                yield ln; c += 1
            sh.close_gen(it)
    return _g()


def cmd_tail(sh, a, inp):
    fl, pos = sh.opts(a, "n", "tail"); n = min(500, sh.int_opt(fl, "n", 10, "tail"))
    def _g():
        if pos:
            for f in pos:
                for ln in sh.read_tail(sh.need_file("tail", f), n, tick=sh.tick):
                    yield ln
        elif inp is not None:
            ring = []
            for ln in inp:
                ring.append(ln)
                if len(ring) > n:
                    ring.pop(0)
            for ln in ring:
                yield ln
        else:
            raise sh.Error("tail: missing file")
    return _g()


def cmd_grep(sh, a, inp):
    fl, pos = sh.opts(a, "", "grep")
    if not pos:
        raise sh.Error("grep: PAT [FILE...]")
    pat, files = pos[0], pos[1:]
    ic, num, inv, cnt = "i" in fl, "n" in fl, "v" in fl, "c" in fl
    nd = pat.lower() if ic else pat
    def _g():
        hits = 0
        for lbl, it in _srcs(sh, "grep", files, inp):
            n = c = 0
            for ln in it:
                n += 1
                if (nd in (ln.lower() if ic else ln)) != inv:
                    c += 1
                    if not cnt:
                        yield ("{}:".format(n) if num else "") + ln
                sh.tick()
            hits += c
            if cnt:
                yield str(c)
        if hits == 0:
            sh.rc_hint = 1
    return _g()


def cmd_wc(sh, a, inp):
    fl, pos = sh.opts(a, "", "wc")
    wl, ww, wc = "l" in fl, "w" in fl, "c" in fl
    if not (wl or ww or wc):
        wl = ww = wc = True
    def fmt(l, w, c, lbl):
        p = ([str(l)] if wl else []) + ([str(w)] if ww else []) + ([str(c)] if wc else [])
        return " ".join(["{:>6}".format(x) for x in p]) + ((" " + lbl) if lbl else "")
    def _g():
        if pos:
            for fn in pos:
                p = sh.need_file("wc", fn); l = w = c = 0; inw = False
                with open(p, "rb") as f:
                    while True:
                        ch = f.read(sh.CHUNK)
                        if not ch:
                            break
                        c += len(ch); l += ch.count(b"\n"); pts = ch.split(); w += len(pts)
                        if inw and pts and ch[0] not in b" \t\r\n":
                            w -= 1
                        inw = ch[-1] not in b" \t\r\n"; sh.tick()
                yield fmt(l, w, c, fn)
        elif inp is not None:
            l = w = c = 0
            for ln in inp:
                l += 1; w += len(ln.split()); c += len(ln) + 1
            yield fmt(l, w, c, "")
    return _g()


def cmd_mkdir(sh, a, inp):
    fl, pos = sh.opts(a, "", "mkdir")
    if not pos:
        raise sh.Error("mkdir: missing operand")
    for t in pos:
        p = sh.path(t)
        if "p" in fl:
            cur = ""
            for s in p.split("/"):
                if s:
                    cur += "/" + s
                    if not sh.is_dir(cur):
                        os.mkdir(cur)
        else:
            os.mkdir(p)


def _guard(sh, cmd, p):
    pp = p.rstrip("/") or "/"
    if pp in sh.PROTECTED:
        raise sh.Error("{}: refusing to modify protected '{}'".format(cmd, pp))


def _rm_tree(sh, p):
    for nm in os.listdir(p):
        c = sh.join(p, nm)
        _rm_tree(sh, c) if sh.is_dir(c) else os.remove(c)
        sh.tick()
    os.rmdir(p)


def cmd_rm(sh, a, inp):
    fl, pos = sh.opts(a, "", "rm"); rec = "r" in fl or "R" in fl; frc = "f" in fl
    if not pos:
        raise sh.Error("rm: missing operand")
    for t in pos:
        p = sh.path(t); _guard(sh, "rm", p); st = sh.stat_of(p)
        if st is None:
            if not frc:
                raise sh.Error("rm: {}: No such file".format(t))
        elif st[0] & 0x4000:
            if not rec:
                raise sh.Error("rm: {}: Is a directory".format(t))
            _rm_tree(sh, p)
        else:
            os.remove(p)


def _cp_file(sh, s, d):
    with open(s, "rb") as fi:
        with open(d, "wb") as fo:
            while True:
                b = fi.read(sh.CHUNK)
                if not b:
                    break
                fo.write(b); sh.tick()


def cmd_cp(sh, a, inp):
    fl, pos = sh.opts(a, "", "cp")
    if len(pos) < 2:
        raise sh.Error("cp: SRC DST")
    dst = sh.path(pos[-1]); isd = sh.is_dir(dst)
    for s in pos[:-1]:
        sp = sh.path(s)
        _cp_file(sh, sp, sh.join(dst, sh.basename(sp)) if isd else dst)


def cmd_mv(sh, a, inp):
    if len(a) < 2:
        raise sh.Error("mv: SRC DST")
    dst = sh.path(a[-1]); isd = sh.is_dir(dst)
    for s in a[:-1]:
        sp = sh.path(s); _guard(sh, "mv", sp)
        d = sh.join(dst, sh.basename(sp)) if isd else dst
        try:
            os.rename(sp, d)
        except OSError:
            _cp_file(sh, sp, d); os.remove(sp)


def cmd_hexdump(sh, a, inp):
    fl, pos = sh.opts(a, "ns", "hexdump")
    if not pos:
        raise sh.Error("hexdump: FILE")
    p = sh.need_file("hexdump", pos[0])
    skip, lim = sh.int_opt(fl, "s", 0, "hexdump"), sh.int_opt(fl, "n", 256, "hexdump")
    def _g():
        with open(p, "rb") as f:
            if skip:
                f.seek(skip)
            off, rem = skip, lim
            while rem > 0:
                ch = f.read(min(sh.CHUNK, rem))
                if not ch:
                    break
                for i in range(0, len(ch), 8):
                    r = ch[i:i + 8]
                    yield "{:06x}: {:<23} |{}|".format(
                        off + i, " ".join(["{:02x}".format(c) for c in r]),
                        "".join([chr(c) if 32 <= c < 127 else "." for c in r]))
                off += len(ch); rem -= len(ch); sh.tick()
    return _g()


def cmd_edit(sh, a, inp):
    if not a:
        raise sh.Error("edit: FILE")
    h = sh.handlers.get("edit")
    if not h:
        raise sh.Error("edit: no UI")
    msg = h(sh.path(a[0]))
    return (msg,) if msg else None


def cmd_help(sh, a, inp):
    nms = sorted(sh.commands)
    return [("c", "PinhOS BusyBox sh ({} cmds)".format(len(nms)))] + sh.format_columns(nms)


SYS_COMMANDS = {
    "ls": cmd_ls, "ll": lambda sh, a, i: cmd_ls(sh, ["-l"] + list(a), i),
    "pwd": lambda sh, a, i: (sh.cwd,), "cd": cmd_cd,
    "echo": lambda sh, a, i: (" ".join(a[1:] if (a and a[0] == "-n") else a),),
    "cat": cmd_cat, "head": cmd_head, "tail": cmd_tail, "grep": cmd_grep, "wc": cmd_wc,
    "mkdir": cmd_mkdir, "rm": cmd_rm,
    "rmdir": lambda sh, a, i: ([_guard(sh, "rmdir", sh.path(t)) or os.rmdir(sh.path(t)) for t in a] and None),
    "cp": cmd_cp, "mv": cmd_mv,
    "touch": lambda sh, a, i: ([open(sh.path(t), "a").close() for t in a if sh.stat_of(sh.path(t)) is None] and None),
    "hexdump": cmd_hexdump, "hd": cmd_hexdump, "edit": cmd_edit, "nano": cmd_edit,
    "clear": lambda sh, a, i: sh.scrollback.clear(), "cls": lambda sh, a, i: sh.scrollback.clear(),
    "exit": lambda sh, a, i: setattr(sh, "exit_requested", True),
    "quit": lambda sh, a, i: setattr(sh, "exit_requested", True),
    "history": lambda sh, a, i: ["{:>3} {}".format(k + 1, l) for k, l in enumerate(sh.line.hist)],
    "env": lambda sh, a, i: ["{}={}".format(k, sh.env[k]) for k in sorted(sh.env)] + ["PWD=" + sh.cwd],
    "help": cmd_help,
    "free": cmd_free, "ps": cmd_ps, "df": cmd_df, "uptime": cmd_uptime,
    "dmesg": cmd_dmesg, "log": cmd_dmesg, "uname": cmd_uname, "ver": cmd_ver,
    "bat": cmd_bat, "bl": cmd_bl, "kbl": cmd_kbl, "theme": cmd_theme,
    "mode": cmd_mode, "date": cmd_date, "reboot": cmd_reboot,
    "hwinfo": cmd_hwinfo, "i2cscan": cmd_i2cscan, "com4": cmd_com4,
}

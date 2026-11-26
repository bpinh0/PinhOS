# PinhOS Phase 3 — On-Device Self-Test Gates 9 & 10 (tests/selftest_p3.py)
# Loaded on-demand by tests/selftest.py and purged immediately to keep peak SRAM low.

import os
import sys
import gc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_busybox_shell(root="/sd/pinhos"):
    """
    Gate 9: BusyBox shell engine + streaming file commands.
    Tests ls, pwd, echo > file, cat | grep, head/tail/wc/hexdump, df, free, rm + safety,
    20-entry history ring, tab-completion, and < 2 KB SRAM delta.
    """
    from boards import get_board
    from tools.shell import Shell, LineInput, tokenize, parse, HIST_MAX
    from core.theme import ThemeManager

    board = get_board()
    root = root.rstrip("/")
    work = root + "/logs/_sh_gate"
    tmp = root + "/tmp_test.txt"

    def run(sh, line):
        lines = []
        rc = sh.run_line(line, out=lambda text, tag=" ": lines.append(text))
        return rc, lines

    def cleanup(sh):
        for ln in ("rm -f " + tmp, "rm -rf " + work):
            sh.run_line(ln, out=lambda text, tag=" ": None)

    def exercise(sh):
        toks = tokenize('echo "a b" \'c d\' ; ls | grep x >> out.txt')
        _assert([t[1] for t in toks if t[0] == "w"] == ["echo", "a b", "c d", "ls", "grep", "x", "out.txt"], "tokenize mismatch")
        pipes = parse(toks)
        _assert(len(pipes) == 2 and pipes[1][1]["redir"] == (">>", "out.txt"), "parse mismatch")

        rc, out = run(sh, "pwd")
        _assert(rc == 0 and out == [root], "pwd mismatch: " + repr(out))
        rc, out = run(sh, "ls")
        _assert(rc == 0 and any("main.py" in x for x in out), "ls missing main.py")
        rc, out = run(sh, "ls -l tools")
        _assert(rc == 0 and any("shell.py" in x for x in out), "ls -l tools missing shell.py")

        rc, out = run(sh, "echo hello pinhos > " + tmp)
        _assert(rc == 0 and out == [], "echo > failed")
        run(sh, 'echo "err: disk full" >> ' + tmp)
        run(sh, "echo fine >> " + tmp)
        rc, out = run(sh, "cat " + tmp + " | grep err")
        _assert(rc == 0 and out == ["err: disk full"], "cat | grep mismatch: " + repr(out))
        rc, out = run(sh, "cat " + tmp + " | grep -i HELLO | wc -l")
        _assert(out and out[0].strip() == "1", "pipe wc -l mismatch: " + repr(out))
        rc, out = run(sh, "echo one; echo two")
        _assert(out == ["one", "two"], "';' chain mismatch")

        big = work + "/big.txt"
        with open(big, "w") as f:
            for i in range(120):
                f.write("line {:03d} lorem ipsum\n".format(i))
        rc, out = run(sh, "head -n 2 " + big)
        _assert(out == ["line 000 lorem ipsum", "line 001 lorem ipsum"], "head mismatch")
        rc, out = run(sh, "tail -n 2 " + big)
        _assert(out == ["line 118 lorem ipsum", "line 119 lorem ipsum"], "tail mismatch")
        rc, out = run(sh, "hexdump -n 16 " + big)
        _assert(len(out) == 2 and all(len(x) <= 53 for x in out), "hexdump mismatch")

        rc, out = run(sh, "df")
        _assert(rc == 0 and any("/sd" in x for x in out), "df mismatch: " + repr(out))
        rc, out = run(sh, "free")
        _assert(rc == 0 and any(x.startswith("Mem:") for x in out), "free mismatch: " + repr(out))
        for cmd in ("uname -a", "ver", "uptime", "bat", "bl", "ps", "dmesg -n 3", "hwinfo", "i2cscan", "theme", "help"):
            rc, out = run(sh, cmd)
            _assert(rc == 0 and len(out) >= 1, "'{}' failed: {}".format(cmd, repr(out)))

        for victim in ("/", "/sd", "/sd/pinhos"):
            rc, out = run(sh, "rm -rf " + victim)
            _assert(rc == 1 and "refusing" in out[0], "rm guard failed on " + victim)
        rc, out = run(sh, "rm " + tmp)
        _assert(rc == 0, "rm tmp failed")

        li = LineInput()
        for i in range(25):
            li.push_history("cmd {}".format(i))
        _assert(len(li.hist) == HIST_MAX == 20 and li.hist[0] == "cmd 5", "history cap failed")
        nl, np_, _c = sh.complete("ca", 2)
        _assert(nl == "cat " and np_ == 4, "cmd tab-complete failed")
        nl, np_, _c = sh.complete("ls /sd/pinhos/to", 16)
        _assert(nl == "ls /sd/pinhos/tools/", "path tab-complete failed: " + repr(nl))

        # Regression test for sh.on_output / _sb_out (no MicroPython list.__setitem__ AttributeError)
        sc_test = [5]
        def _test_on_out():
            sc_test[0] = 0
        sh.on_output = _test_on_out
        sh.run_line("echo on_output_ok")
        sh.on_output = None
        _assert(sc_test[0] == 0 and any("on_output_ok" in r for r in sh.scrollback.lines), "sh.on_output regression failed")

    sh = Shell(board=board, theme_mgr=ThemeManager(themes_dir=root + "/themes", config=None, board=board), cwd=root)
    try:
        try:
            os.mkdir(work)
        except OSError:
            pass
        cleanup(sh)
        try:
            os.mkdir(work)
        except OSError:
            pass
        exercise(sh)
        gc.collect(); gc.collect()
        m0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        exercise(sh)
        cleanup(sh)
        sh.scrollback.clear()
        del sh
        gc.collect(); gc.collect()
        m1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        delta = max(0, m0 - m1)
        _assert(delta < 2048, "BusyBox SRAM delta {}B >= 2048B".format(delta))
    finally:
        for mn in ("tools.shell", "tools._shell_cmds"):
            sys.modules.pop(mn, None)
        gc.collect()
        board.ensure_serial_repl()

    return "ls/pwd/echo>/cat|grep/df/free/rm OK (d={}B)".format(delta)


def test_phase3_field_tools(root="/sd/pinhos"):
    """
    Gate 10: Static APP_META inspection of all 6 tools/*.py + streaming File Manager,
    Text Editor, Net Probes WoL, HAL UART1 open/close, and SysMon SD benchmark (< 2 KB delta).
    """
    from boards import get_board
    from core.sandbox import inspect_app

    board = get_board()
    root = root.rstrip("/")
    for rel in ("tools/shell.py", "tools/editor.py", "tools/files.py",
                "tools/net_tools.py", "tools/uart_term.py", "tools/sysmon.py"):
        meta = inspect_app(root + "/" + rel)
        _assert(meta.get("entry") == "main" and meta.get("min_sram", 0) >= 16384, "Bad APP_META in " + rel)

    tmp_f = root + "/logs/_gate10_ed.json"
    bres = {"write_kbps": 0, "read_kbps": 0}
    try:
        def _run_one(mod_name, fn):
            gc.collect()
            m = __import__(mod_name, None, None, ("*",))
            try:
                return fn(m)
            finally:
                m = None
                sys.modules.pop(mod_name, None)
                gc.collect()

        def _exercise():
            def _t_files(tf):
                ents = tf.list_dir_entries(root + "/tools")
                _assert(any(e["name"] == "shell.py" for e in ents), "files list missing shell.py")
                lns, nb = tf.read_text_preview(root + "/version.json", max_bytes=1024)
                _assert(nb > 20 and len(lns) >= 3, "files text preview failed")
                hx = tf.read_hex_preview(root + "/version.json", max_bytes=32)
                _assert(len(hx) == 4 and all(len(r) <= 53 for r in hx), "files hex preview failed")
            _run_one("tools.files", _t_files)

            def _t_ed(te):
                with open(tmp_f, "w") as f:
                    f.write('{"gate": 10}\n')
                ed = te.Editor(board, None, tmp_f)
                ed.load()
                _assert(ed.lines and '"gate": 10' in ed.lines[0], "Editor.load failed")
                ed.lines = ['{"gate": 10, "ok": true}']
                _assert(ed.save(), "Editor.save valid JSON failed")
                ed.lines = ['{broken']
                _assert(not ed.save(), "Editor.save should warn on bad JSON")
            _run_one("tools.editor", _t_ed)

            def _t_net(tn):
                pkt = tn.build_wol_packet("AA:BB:CC:DD:EE:FF")
                _assert(len(pkt) == 102 and pkt[:6] == b"\xff" * 6, "WoL packet invalid")
                _assert(isinstance(tn.get_wifi_status(), dict), "wifi status failed")
            _run_one("tools.net_tools", _t_net)

            def _t_uart(tu):
                board.open_aux_uart(115200)
                board.close_aux_uart()
                _assert(tu.format_rx_chunk(b"AB", hex_mode=True)[0].startswith("41 42"), "UART hex fmt failed")
            _run_one("tools.uart_term", _t_uart)

            def _t_sys(ts):
                r = ts.run_sd_benchmark(8)
                _assert(r["ok"] and r["write_kbps"] > 0 and r["read_kbps"] > 0, "SD bench failed")
                return r
            res_sys = _run_one("tools.sysmon", _t_sys)
            return res_sys

        _exercise()
        gc.collect(); gc.collect()
        m0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        bres = _exercise()
        gc.collect(); gc.collect()
        m1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        delta = max(0, m0 - m1)
        _assert(delta < 2048, "Field tools SRAM delta {}B >= 2048B".format(delta))

        # Verify CTRL+P screenshot + confirmation toast and non-blocking CTRL+Q LNK mode
        for _um in (
            "core.sandbox", "core.theme", "ui.widgets", "ui.gui", "ui.tui", "ui.engine",
            "tools.files", "tools.editor", "tools.net_tools", "tools.uart_term", "tools.sysmon",
        ):
            sys.modules.pop(_um, None)
        gc.collect(); gc.collect()
        import main as _pm
        _ui = _pm.runtime_state.get("ui")
        if _ui is None:
            _, _ui = _pm._ensure_ui_services(board)
        shot_p = board.screenshot()
        _assert(shot_p and shot_p.endswith(".bmp"), "screenshot capture failed")
        on1, m1_s = _pm.toggle_serial_link(board, enable=True)
        _assert(on1 and _pm.runtime_state.get("serial_link") is True and "LNK ON" in m1_s, "LNK enable failed")
        _assert(_pm._enter_sleep_mode(board, _ui, None, countdown_s=1) is False, "LNK should suppress sleep")
        on2, m2_s = _pm.toggle_serial_link(board, enable=False)
        _assert((not on2) and _pm.runtime_state.get("serial_link") is False, "LNK disable failed")
        _pm = None
        sys.modules.pop("main", None)
        sys.modules.pop("_pinhos_main", None)
        gc.collect(); gc.collect()
        from ui.widgets import show_screenshot_toast
        fn, smsg = show_screenshot_toast(board, _ui, path=shot_p, timeout_ticks=1)
        _assert(fn and fn.startswith("shot_") and "Saved:" in str(smsg), "screenshot toast failed")
        try:
            os.remove(shot_p)
        except OSError:
            pass
        gc.collect()
    finally:
        try:
            os.remove(tmp_f)
        except OSError:
            pass
        board.close_aux_uart()
        board.ensure_serial_repl()

    return "6 tools OK | SD W:{}K/s R:{}K/s (d={}B)".format(bres["write_kbps"], bres["read_kbps"], delta)


def test_desktop_home(root="/sd/pinhos"):
    """Gate 11: Desktop Home (GUI+TUI), L/R Quick-Strip, [F1] Help, Theme Schema v2 + 6x8 Fonts & Notes <= 1 KB."""
    # 1. Verify 6-category Settings tree + NTP resync & WDT log picker on a clean heap, then unload ui.menu
    gc.collect(); gc.collect()
    from ui.menu import MENU_TREE
    set_entry = MENU_TREE.get("settings", ("", ()))
    set_items = set_entry[1] if isinstance(set_entry, tuple) and len(set_entry) >= 2 else ()
    set_ids = [it.get("id") for it in set_items if isinstance(it, dict)]
    for req in ("cat:set_conn", "cat:set_time", "cat:set_display", "cat:set_bar_snd", "cat:set_power", "cat:set_about"):
        _assert(req in set_ids, "Missing settings category: " + req)
    _assert(len(set_items) == 6, "Expected 6 settings categories, got {}".format(len(set_items)))
    time_items = MENU_TREE.get("set_time", ("", ()))[1]
    _assert(any(it.get("id") == "ntp:resync" for it in time_items), "Missing ntp:resync in set_time")
    MENU_TREE = None
    set_items = None
    time_items = None
    sys.modules.pop("ui.menu", None)

    import ui._log_view as _lv
    log_names = [it.get("name") for it in _lv._list_logs(root.rstrip("/") + "/logs")]
    _assert("wdt.log" in log_names, "wdt.log missing from _log_view._list_logs")
    _lv = None
    sys.modules.pop("ui._log_view", None)
    gc.collect(); gc.collect()

    from boards import get_board
    from core.config import ConfigManager
    from core.theme import Theme, ThemeManager
    from ui.fonts import get_font, FONT_BYTES
    from ui.engine import UIEngine
    from ui.desktop import DesktopHome, show_help_dialog, load_notes, save_notes, append_note, NOTES_MAX_BYTES

    board = get_board()
    board.ensure_serial_repl()

    # Verify all 3 built-in 6x8 fonts are exact 570 B & missing .bin falls back safely
    for fname in ("default", "bold", "retro"):
        mv, rname = get_font(fname, fonts_dir=root.rstrip("/") + "/fonts")
        _assert(rname == fname and len(mv) == FONT_BYTES, "Font '{}' invalid size {}".format(fname, len(mv)))
    mv_fb, r_fb = get_font("nonexistent_custom_font", fonts_dir=root.rstrip("/") + "/fonts")
    _assert(r_fb == "default" and len(mv_fb) == FONT_BYTES, "Missing font did not fall back to default")

    # 2. Quick Notes streaming R/W roundtrip + <= 1 KB cap enforcement
    tmp_notes = root.rstrip("/") + "/logs/_gate11_notes.txt"
    tmp_cfg = root.rstrip("/") + "/logs/_gate11_cfg.json"
    delta = 0
    try:
        _assert(save_notes(["Alpha note", "Beta note"], path=tmp_notes), "save_notes failed")
        _assert(append_note("Gamma note", path=tmp_notes), "append_note failed")
        got = load_notes(path=tmp_notes)
        _assert(got == ["Alpha note", "Beta note", "Gamma note"], "notes roundtrip mismatch: " + repr(got))

        # Enforce <= 1024 B streaming cap
        big = ["Note line {:02d} {}".format(i, "X" * 60) for i in range(25)]
        _assert(save_notes(big, path=tmp_notes), "save_notes cap failed")
        st = os.stat(tmp_notes)
        _assert(st[6] <= NOTES_MAX_BYTES, "notes.txt exceeded 1024B cap: {}B".format(st[6]))
        capped = load_notes(path=tmp_notes)
        _assert(len(capped) >= 5 and "Note line 24" in capped[-1], "newest note lost under cap")

        # 3. DesktopHome GUI + TUI, L/R Quick-Strip partial redraw, [F1] Help & Theme Schema v2 (< 2048 B delta)
        def _render_once():
            cfg = ConfigManager(config_path=tmp_cfg)
            tm = ThemeManager(themes_dir=root.rstrip("/") + "/themes", config=cfg, board=board)
            ui = UIEngine(board=board, theme_manager=tm, config=cfg)
            dh = DesktopHome(0, 22, 320, 252, notes_path=tmp_notes)
            ui.add_widget(dh)
            ui.set_focus(dh)

            # Render both WEB ON and WEB OFF telemetry states in GUI & TUI
            dh.sync_telemetry(board, ui_mode="GUI", drawer_layout="GRID", stabilized=True, web_active=True)
            ui.set_mode("gui", persist=False)
            ui.render(force=True)

            # Exercise LEFT/RIGHT quick-strip cycling (0 <-> 5 wrap-around) + partial strip redraw
            _assert(dh.strip_sel is None, "Initial strip_sel must be None")
            _assert(ui.handle_key("RIGHT", allow_hotkeys=False) == "handled" and dh.strip_sel == 0, "RIGHT->0 failed")
            ui.render(force=False)
            _assert(not ui.last_render_full and dh.last_partial_strip, "Quick-strip RIGHT did not partial-redraw")
            _assert(dh.get_selected_action() == "cat:toolkit", "Pill 0 action mismatch")
            _assert(ui.handle_key("LEFT", allow_hotkeys=False) == "handled" and dh.strip_sel == 5, "LEFT wrap 0->5 failed")
            ui.render(force=False)
            _assert(not ui.last_render_full and dh.get_selected_action() == "cat:set_conn", "Pill 5 wrap mismatch")
            _assert(ui.handle_key("RIGHT", allow_hotkeys=False) == "handled" and dh.strip_sel == 0, "RIGHT wrap 5->0 failed")
            _assert(ui.handle_key("DOWN", allow_hotkeys=False) == "handled" and dh.strip_sel is None, "DOWN unselect failed")
            ui.render(force=False)

            # Exercise [F1] Help dialog open + dismiss via queued F1 key
            board.clear_input()
            board.push_event({"type": "key", "key": "F1", "modifiers": 0})
            _assert(show_help_dialog(board, ui), "show_help_dialog failed")
            ui.render(force=False)

            # Exercise Theme Schema v2 (Obsidian Amber bold font + custom retro/rounded/banner theme)
            tm.apply("obsidian_amber", persist=False)
            ui.render(force=False)
            custom_v2 = Theme({
                "id": "retro_test",
                "name": "Retro Test",
                "version": 2,
                "font": "retro",
                "uppercase_headers": True,
                "colors": {"bg": "#090A0D", "surface": "#111318", "text": "#F4F5F7", "accent": "#10B981"},
                "style": {"border_style": "rounded", "bar_style": "striped", "card_header": "tinted", "quick_strip": "tabs"},
                "banner": ["=== PINHOS V2 ===", "RETRO BANNER OK"],
            })
            tm.active = custom_v2
            tm._push_to_board(custom_v2)
            dh.set_strip_sel(2)
            ui.mark_all_dirty(True)
            ui.render(force=True)

            dh.sync_telemetry(board, ui_mode="TUI", drawer_layout="LIST", stabilized=True, web_active=False)
            ui.set_mode("tui", persist=False)
            ui.render(force=True)

            tm.apply("cyber_amber", persist=False)
            ui.deinit()

        _render_once()
        gc.collect(); gc.collect()
        m0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        _render_once()
        gc.collect(); gc.collect()
        m1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        delta = max(0, m0 - m1)
        _assert(delta < 2048, "DesktopHome SRAM delta {}B >= 2048B".format(delta))
    finally:
        for p in (tmp_notes, tmp_notes + ".tmp", tmp_cfg):
            try:
                os.remove(p)
            except OSError:
                pass
        board.ensure_serial_repl()

    return "Home+L/R+F1+SchemaV2+Notes<=1KB (d={}B)".format(delta)

# PinhOS Phase 3 — Hierarchical Launcher Menu, Android-Style Settings Tree & Log Viewer (ui/menu.py)
# Declarative lightweight dicts/tuples; reuses 2-row dirty ListMenu for < 2 KB SRAM delta.
# Zero hardcoded GPIO pins; all input polled via board.poll_key().

import os
import gc
import time


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


DASHBOARD_ACTIONS = (
    {"id": "cat:toolkit", "short": "TOOLKIT", "label": "TERMINAL & TOOLKIT", "icon": "term", "badge": "[1]", "tui_badge": "[SH >]"},
    {"id": "cat:files", "short": "FILES & EDIT", "label": "FILES & EDITOR", "icon": "files", "badge": "[2]", "tui_badge": "[/sd >]"},
    {"id": "cat:apps", "short": "APPS & STUDIO", "label": "APPS & STUDIO", "icon": "apps", "badge": "[3]", "tui_badge": "[APPS >]"},
    {"id": "cat:system", "short": "SYS & DIAG", "label": "SYSTEM & DIAGNOSTICS", "icon": "dash", "badge": "[4]", "tui_badge": "[DIAG >]"},
    {"id": "cat:settings", "short": "SETTINGS", "label": "SETTINGS", "icon": "sys", "badge": "[5]", "tui_badge": "[CFG >]"},
    {"id": "cat:set_conn", "short": "WI-FI & NET", "label": "WI-FI & NETWORK", "icon": "net", "badge": "[6]", "tui_badge": "[NET >]"},
)

MENU_TREE = {
    "toolkit": ("Toolkit", (
        {"id": "tool:shell", "label": "BusyBox Shell (sh)", "badge": "[B]"},
        {"id": "tool:uart", "label": "UART Serial Console", "badge": "[U]"},
        {"id": "tool:net", "label": "Net Probes", "badge": "[N]"},
    )),
    "files": ("Files & Editor", (
        {"id": "tool:files", "label": "File Manager (/sd)", "badge": "[F]"},
        {"id": "tool:editor", "label": "Text / Config Editor", "badge": "[E]"},
    )),
    "system": ("System & Diag", (
        {"id": "tool:sysmon", "label": "System Monitor", "badge": "[S]"},
        {"id": "act:logs", "label": "System & Web Logs", "badge": "[L]"},
        {"id": "act:selftest", "label": "Run Self-Test", "badge": "[S-F10]"},
    )),
    "settings": ("Settings", (
        {"id": "cat:set_conn", "label": "Wi-Fi & Connectivity", "dyn": "conn_badge"},
        {"id": "cat:set_time", "label": "Date, Time & NTP", "dyn": "time_badge"},
        {"id": "cat:set_display", "label": "Display & Appearance", "dyn": "ui_summary"},
        {"id": "cat:set_bar_snd", "label": "Status Bar & Sound", "dyn": "bar_snd_badge"},
        {"id": "cat:set_power", "label": "System, Power & Backup", "dyn": "power_badge"},
        {"id": "cat:set_about", "label": "About PinhOS", "dyn": "os_ver"},
    )),
    "set_conn": ("Wi-Fi & Connectivity", (
        {"id": "wifi:status", "label": "Wi-Fi Status", "dyn": "wifi_st"},
        {"id": "wifi:scan", "label": "Scan & Connect", "badge": "[SCAN]"},
        {"id": "wifi:saved", "label": "Saved Networks", "badge": "[LIST]"},
        {"id": "wifi:auto", "label": "Auto-Connect Boot", "dyn": "wifi_auto"},
        {"id": "wifi:country", "label": "Wi-Fi Country Code", "dyn": "wifi_cc"},
        {"id": "wifi:off", "label": "Disconnect Wi-Fi", "badge": "[OFF]"},
        {"id": "web:toggle", "label": "WebPortal IDE", "dyn": "web_st"},
        {"id": "web:info", "label": "WebPortal URL & Token", "badge": "[KEY]"},
        {"id": "web:auto", "label": "Auto-Start WebPortal", "dyn": "web_auto"},
        {"id": "sync:check", "label": "GitHub: Check OS Version", "badge": "[VER]"},
        {"id": "sync:themes", "label": "GitHub: Sync Themes", "badge": "[JSON]"},
        {"id": "sync:apps", "label": "GitHub: Sync Apps", "badge": "[PY]"},
    )),
    "set_time": ("Date, Time & NTP", (
        {"id": "ntp:sync", "label": "Sync NTP Clock Now", "badge": "[NTP]"},
        {"id": "ntp:auto", "label": "Auto-NTP on Wi-Fi", "dyn": "ntp_auto"},
        {"id": "ntp:resync", "label": "NTP Resync Interval", "dyn": "ntp_resync"},
        {"id": "ntp:tz", "label": "Timezone Offset", "dyn": "tz_off"},
        {"id": "rtc:date", "label": "Set Date (Manual)", "dyn": "rtc_date"},
        {"id": "rtc:time", "label": "Set Time (Manual)", "dyn": "rtc_time"},
    )),
    "set_display": ("Display & Appearance", (
        {"id": "cat:set_theme", "label": "Theme", "dyn": "theme_name"},
        {"id": "set:mode", "label": "UI Mode", "dyn": "ui_mode"},
        {"id": "set:layout", "label": "App Drawer Style", "dyn": "layout"},
        {"id": "set:boot_scr", "label": "Boot Screen", "dyn": "boot_scr"},
        {"id": "set:lcd_bl", "label": "LCD Backlight", "dyn": "lcd_bl"},
        {"id": "set:kb_bl", "label": "KB Backlight", "dyn": "kb_bl"},
    )),
    "set_bar_snd": ("Status Bar & Sound", (
        {"id": "set:wifi_ind", "label": "Wi-Fi Indicator", "dyn": "wifi_ind"},
        {"id": "set:bat_ind", "label": "Battery Indicator", "dyn": "bat_ind"},
        {"id": "set:sound", "label": "Key Sound / Beep", "dyn": "sound"},
    )),
    "set_power": ("System, Power & Backup", (
        {"id": "set:cpu_mhz", "label": "CPU Clock Profile", "dyn": "cpu_mhz"},
        {"id": "set:swap_kb", "label": "SD Swap Quota", "dyn": "swap_kb"},
        {"id": "act:swap_clr", "label": "Clear Swap Cache", "dyn": "swap_used"},
        {"id": "set:sleep_to", "label": "Auto-Sleep Timer", "dyn": "sleep_to"},
        {"id": "set:wdt_to", "label": "Hardware Watchdog", "dyn": "wdt_to"},
        {"id": "act:sleep", "label": "Sleep Now (5s)", "badge": "[^Z]"},
        {"id": "cfg:save_snap", "label": "Save Config Snapshot", "badge": "[SD]"},
        {"id": "cfg:load_snap", "label": "Restore Config Snapshot", "dyn": "snap_st"},
        {"id": "info:bat_rtc", "label": "Battery & RTC Info", "dyn": "bat_pct"},
        {"id": "act:reboot", "label": "Reboot PinhOS", "badge": "[RST]"},
        {"id": "act:repl", "label": "COM4 Serial Link", "dyn": "serial_link"},
    )),
    "set_about": ("About PinhOS", (
        {"id": "info:version", "label": "OS & UF2 Version", "dyn": "os_ver"},
        {"id": "info:board", "label": "Board & SRAM Summary", "dyn": "sram_kb"},
    )),
}

TOOL_MAP = {
    "shell": ("/sd/pinhos/tools/shell.py", "BusyBox Shell", False),
    "editor": ("/sd/pinhos/tools/editor.py", "Text Editor", False),
    "files": ("/sd/pinhos/tools/files.py", "File Manager", False),
    "net": ("/sd/pinhos/tools/net_tools.py", "Net Probes", False),
    "uart": ("/sd/pinhos/tools/uart_term.py", "UART Console", False),
    "sysmon": ("/sd/pinhos/tools/sysmon.py", "SysMon", False),
}


def _idle_wait(ms=30):
    try:
        import sys
        _w = sys.modules.get("__pinhos_wdt__")
        if _w is not None:
            _w.feed()
        m = sys.modules.get("main") or sys.modules.get("_pinhos_main")
        if m and getattr(m, "runtime_state", {}).get("web_active") and hasattr(m, "step_webportal"):
            m.step_webportal(20)
            return
    except Exception:
        pass
    _sleep_ms(ms)


def confirm_dialog(board, ui, title, lines, footer="[Y/ENTER] Yes  [N/ESC] No", kind="warn"):
    """Lightweight modal confirmation Dialog. Polls board.poll_key() only."""
    from ui.widgets import Dialog
    dlg = Dialog(20, 96, 280, 120, title=title, lines=lines, footer=footer, kind=kind)
    ui.add_widget(dlg)
    ui.render(force=False)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    ans = False
    try:
        while True:
            k = poll_fn() if poll_fn else None
            if k:
                ku = str(k).upper()
                if ku in ("Y", "ENTER"):
                    ans = True; break
                if ku in ("N", "ESC", "Q", "BACK", "BACKSPACE"):
                    break
            _idle_wait(30)
    except KeyboardInterrupt:
        ans = False
    ui.remove_widget(dlg)
    ui.mark_all_dirty(True)
    board.clear_input()
    return ans


def show_info_dialog(board, ui, title, lines, kind="info"):
    """Modal informational Dialog dismissed by ENTER/ESC/BACKSPACE."""
    from ui.widgets import Dialog
    dlg = Dialog(16, 70, 288, 176, title=title, lines=lines, footer="[ENTER/ESC/BS] Back", kind=kind)
    ui.add_widget(dlg)
    ui.render(force=False)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            k = poll_fn() if poll_fn else None
            if k and str(k).upper() in ("ENTER", "ESC", "SPACE", " ", "BACK", "BACKSPACE"):
                board.beep(1000, 10); break
            _idle_wait(30)
    except KeyboardInterrupt:
        pass
    ui.remove_widget(dlg)
    ui.mark_all_dirty(True)
    board.clear_input()


def show_screenshot_toast(board, ui, fb=None, path=None, timeout_ticks=30):
    """
    Brief confirmation toast Dialog shown after CTRL+P captures a clean 320x320 4-bit BMP.
    Returns (fname, status_msg) or (None, None) on failure.
    """
    from ui.widgets import Dialog
    p = path
    if p is None and hasattr(board, "pop_pending_screenshot"):
        p = board.pop_pending_screenshot()
    if p is None and hasattr(board, "screenshot"):
        p = board.screenshot()
    if not p:
        if fb is not None:
            fb.update(status="Screenshot failed (check SD)", status_kind="err")
        return None, None
    fname = str(p).rstrip("/").rpartition("/")[2] or str(p)
    smsg = "Saved: " + fname
    if fb is not None:
        fb.update(status=smsg, status_kind="ok")
    if ui is not None:
        dlg = Dialog(
            18, 92, 284, 128,
            title="SCREENSHOT SAVED",
            lines=[
                "320x320 4-bit Indexed BMP:",
                "  " + fname[:36],
                "Dir: /sd/pinhos/screenshots/",
            ],
            footer="[ANY KEY / 1s] Continue",
            kind="ok",
        )
        ui.add_widget(dlg)
        ui.render(force=False)
        poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
        for _ in range(int(timeout_ticks)):
            if poll_fn and poll_fn() is not None:
                break
            _sleep_ms(30)
        ui.remove_widget(dlg)
        ui.mark_all_dirty(True)
        board.clear_input()
        ui.render(force=True)
    return fname, smsg


def show_toast_dialog(board, ui, title, lines, fb=None, status_msg="", kind="info", timeout_ticks=25):
    """Brief self-dismissing toast Dialog (dismisses immediately on any key or after timeout_ticks)."""
    from ui.widgets import Dialog
    if fb is not None and status_msg:
        fb.update(status=status_msg, status_kind=kind)
    if ui is None or board is None:
        return
    dlg = Dialog(
        24, 96, 272, 120,
        title=title,
        lines=lines,
        footer="[ANY KEY / Auto] OK",
        kind=kind,
    )
    ui.add_widget(dlg)
    ui.render(force=False)
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    for _ in range(max(1, int(timeout_ticks))):
        if poll_fn and poll_fn() is not None:
            break
        _idle_wait(30)
    ui.remove_widget(dlg)
    ui.mark_all_dirty(True)
    board.clear_input()


def open_log_viewer(board, ui, logger, kind="system"):
    import sys
    gc.collect()
    import ui._log_view as _lv
    try:
        return _lv.open_log_viewer(board, ui, logger, kind=kind)
    finally:
        _lv = None
        sys.modules.pop("ui._log_view", None)
        gc.collect()


def _scan_apps(sandbox, apps_dir="/sd/pinhos/apps"):
    import sys
    items = []
    try:
        names = sorted([f for f in os.listdir(apps_dir) if f.endswith(".py") and not f.startswith("_")])
    except OSError:
        names = []
    inspect_fn = sandbox.inspect if sandbox is not None else None
    loaded_sbx = False
    if inspect_fn is None and names:
        try:
            from core.sandbox import inspect_app
            inspect_fn = inspect_app
            loaded_sbx = True
        except Exception:
            inspect_fn = None
    for fname in names:
        fpath = apps_dir.rstrip("/") + "/" + fname
        label, badge = fname[:-3], "[APP]"
        if inspect_fn is not None:
            try:
                meta = inspect_fn(fpath)
                label = str(meta.get("name", label))[:26]
                badge = "v" + str(meta.get("version", "1.0"))[:6]
            except Exception:
                badge = "[RAW]"
        items.append({"id": "app:" + fpath, "label": label, "badge": badge})
    if loaded_sbx:
        inspect_fn = None
        sys.modules.pop("core.sandbox", None)
        gc.collect()
    return items or [{"id": "", "label": "(No apps in /sd/pinhos/apps)", "badge": ""}]


def _dyn_badge(tag, board, ui, manifest, cfg=None):
    if tag == "conn_badge":
        try:
            from net.wifi import get_wifi_manager
            st = get_wifi_manager().status()
            return st["ip"][:13] + " >" if st.get("connected") else "[LAN >]"
        except Exception:
            return "[LAN >]"
    if tag == "bar_snd_badge":
        snd = bool(cfg.get("sound", True) if cfg else True)
        return ("SND:ON >" if snd else "SND:OFF >")
    if tag == "power_badge":
        return "{}% >".format(board.get_battery().get("percent", 0))
    if tag == "boot_scr":
        return "HOME" if str(cfg.get("boot_screen", "desktop") if cfg else "desktop").lower() == "desktop" else "DRAWER"
    if tag == "wifi_st":
        try:
            from net.wifi import get_wifi_manager
            st = get_wifi_manager().status()
            return st["ip"][:15] if st.get("connected") else "OFF"
        except Exception:
            return "OFF"
    if tag == "ui_summary":
        return "{} / {}%".format(ui.mode_badge, board.get_backlight())
    if tag == "bat_pct":
        return "{}%".format(board.get_battery().get("percent", 0))
    if tag == "os_ver":
        return "v" + str(manifest.get("version", "1.0.0-alpha.4.4"))[:11]
    if tag == "theme_name":
        return ui.theme.name.split()[0][:10] + " >"
    if tag == "ui_mode":
        return ui.mode_badge
    if tag == "wifi_auto":
        try:
            from net.wifi import get_wifi_manager
            return "ON" if get_wifi_manager().get_auto_connect() else "OFF"
        except Exception:
            return "OFF"
    if tag == "wifi_cc":
        cc = str(cfg.get("wifi_country", "XX") if cfg else "XX").strip().upper()
        return "XX!" if (len(cc) != 2 or cc == "XX") else cc
    if tag == "ntp_auto":
        return "ON" if (cfg.get("ntp_auto", True) if cfg else True) else "OFF"
    if tag == "ntp_resync":
        sec = int(cfg.get("ntp_resync_s", 3600) if cfg else 3600)
        if sec <= 0:
            return "OFF"
        return "{}h".format(sec // 3600) if sec >= 3600 else "{}m".format(sec // 60)
    if tag == "tz_off":
        tz = int(cfg.get("tz_offset_h", 0) if cfg else 0)
        return "UTC{}{}".format("+" if tz >= 0 else "", tz)
    if tag == "snap_st":
        try:
            return "READY" if (cfg and cfg.has_snapshot()) else "NONE"
        except Exception:
            return "NONE"
    if tag == "cpu_mhz":
        try:
            import machine
            mhz = machine.freq() // 1000000
        except Exception:
            mhz = int(cfg.get("cpu_freq_mhz", 150) if cfg else 150)
        return "{}MHz".format(mhz)
    if tag == "wifi_ind":
        return str(cfg.get("wifi_indicator", "bars") if cfg else "bars").upper().replace("_", "+")
    if tag == "bat_ind":
        return str(cfg.get("battery_indicator", "both") if cfg else "both").upper()
    if tag == "sleep_to":
        sec = int(cfg.get("sleep_timeout_s", 300) if cfg else 300)
        return "OFF" if sec <= 0 else "{}m".format(sec // 60)
    if tag == "wdt_to":
        ms = int(cfg.get("wdt_timeout_ms", 8000) if cfg else 8000)
        return "OFF" if ms <= 0 else "{}s".format(ms // 1000)
    if tag == "sound":
        return "ON" if (cfg.get("sound", True) if cfg else True) else "OFF"
    if tag == "layout":
        return str(cfg.get("launcher_layout", "grid") if cfg else "grid").upper()
    if tag == "lcd_bl":
        return "{}%".format(board.get_backlight())
    if tag == "kb_bl":
        return "{}%".format(board.get_kb_backlight())
    if tag == "sram_kb":
        return "{}KB free".format((gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256)
    if tag == "serial_link":
        try:
            import sys
            m = sys.modules.get("main")
            rs = getattr(m, "runtime_state", {}) if m else {}
            return "LNK ON" if rs.get("serial_link") else "OFF"
        except Exception:
            return "OFF"
    if tag == "web_st":
        try:
            import sys
            m = sys.modules.get("main")
            rs = getattr(m, "runtime_state", {}) if m else {}
            if rs.get("web_active"):
                ws = rs.get("web_server")
                return "ON :{}".format(getattr(ws, "port", 8080))
            return "OFF"
        except Exception:
            return "OFF"
    if tag == "web_auto":
        return "ON" if (cfg.get("webportal_autostart", False) if cfg else False) else "OFF"
    if tag == "time_badge":
        return board.get_timestamp_str(True)[:5] + " >"
    if tag == "rtc_date":
        return board.get_timestamp_str()[:10]
    if tag == "rtc_time":
        return board.get_timestamp_str(True)[:8]
    if tag == "swap_kb":
        kb = int(cfg.get("swap_max_kb", 512) if cfg else 512)
        return "OFF" if kb <= 0 else ("{}MB".format(kb // 1024) if kb >= 1024 else "{}KB".format(kb))
    if tag == "swap_used":
        try:
            from core.swap import get_swap_manager
            st = get_swap_manager().stats()
            return "{}K ({})".format(st.get("used_kb", 0), st.get("files", 0))
        except Exception:
            return "0K"
    return ""


def _prompt_line(board, ui, fb, label, initial="", allowed=None, max_len=16):
    buf = str(initial)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while True:
        fb.update(status="{}: {}_".format(label, buf), status_kind="info", hints="ENT:Save  BKSP:Del  ESC:Cancel")
        ui.render(force=False)
        k = poll_fn() if poll_fn else None
        if k is None:
            _idle_wait(30); continue
        ku = str(k).upper()
        if ku in ("ESC", "BACK"):
            return None
        if ku in ("ENTER", "RETURN"):
            return buf.strip()
        if ku == "BACKSPACE":
            buf = buf[:-1]
        elif len(k) == 1 and len(buf) < max_len:
            if allowed is None or k in allowed:
                buf += k


def _wifi_scan_and_connect(board, ui, sb, lm, fb, cfg=None):
    import sys
    gc.collect()
    import ui._menu_net as _mn
    try:
        return _mn.wifi_scan_and_connect(board, ui, sb, lm, fb, cfg=cfg)
    finally:
        _mn = None
        sys.modules.pop("ui._menu_net", None)
        gc.collect()


def _wifi_saved_menu(board, ui, sb, lm, fb, cfg=None):
    import sys
    gc.collect()
    import ui._menu_net as _mn
    try:
        return _mn.wifi_saved_menu(board, ui, sb, lm, fb, cfg=cfg)
    finally:
        _mn = None
        sys.modules.pop("ui._menu_net", None)
        gc.collect()


def open_menu_tree(board, ui, theme_mgr, cfg, logger, sandbox, manifest, root_cat, run_tool_cb):
    """
    Android-style breadcrumb-backed hierarchical drill-down menu & Settings tree.
    UP/DOWN: 2-row dirty ListMenu nav | ENTER/RIGHT: open | ESC/LEFT: back one level.
    """
    from ui.widgets import StatusBar, ListMenu, FooterBar
    sb = StatusBar(0, 0, 320, 20, title="", mode_label=ui.mode_badge)
    lm = ListMenu(4, 24, 312, 248, title="", items=[], selected=0)
    hints = "UP/DN:Sel  ENT:Open  ESC/BS:Back"
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=hints)

    stack = [[root_cat, 0]]
    status_msg, status_kind = "", "info"
    chg_phase = 0
    menu_ticks = 0

    def _title(nid):
        if nid == "apps":
            return "Apps & Studio"
        if nid == "set_theme":
            return "Theme"
        ent = MENU_TREE.get(nid)
        return ent[0] if ent else nid

    def _items(nid):
        if nid == "apps":
            return _scan_apps(sandbox)
        if nid == "set_theme":
            act = theme_mgr.active.id
            rows = []
            for t in theme_mgr.list_themes():
                lbl = " ".join([w[0].upper() + w[1:] for w in str(t).split("_") if w])
                rows.append({"id": "theme:" + str(t), "label": lbl, "badge": "[*]" if t == act else ""})
            rows.append({"id": "sync:themes", "label": "Sync Themes (GitHub)", "badge": "[SYNC]"})
            return rows
        ent = MENU_TREE.get(nid)
        if not ent:
            return []
        return [{"id": r["id"], "label": r["label"], "badge": _dyn_badge(r["dyn"], board, ui, manifest, cfg) if "dyn" in r else r.get("badge", "")} for r in ent[1]]

    def _update_sb(crumb):
        wf_mode = str(cfg.get("wifi_indicator", "bars") if cfg else "bars").lower()
        wf_lvl, wf_txt = None, ""
        if wf_mode != "off":
            try:
                from net.wifi import get_wifi_bar_info
                wf_lvl, wf_txt = get_wifi_bar_info(wf_mode)
            except Exception:
                wf_lvl, wf_txt = None, ""
        bat = board.get_battery()
        bm = str(cfg.get("battery_indicator", "both") if cfg else "both").lower()
        bat_icon = (bat["percent"], bat["charging"], chg_phase if bat["charging"] else 0) if bm in ("both", "icon") else None
        bat_txt = "{}%".format(bat["percent"]) if bm in ("both", "pct") else ""
        right_s = " ".join([x for x in (wf_txt, bat_txt) if x])
        lnk = False
        web_on = False
        try:
            import sys
            m = sys.modules.get("main")
            if m and isinstance(getattr(m, "runtime_state", None), dict):
                lnk = bool(m.runtime_state.get("serial_link"))
                web_on = bool(m.runtime_state.get("web_active"))
        except Exception:
            pass
        sb.update(title=crumb, mode_label=ui.mode_badge, right_text=right_s, wifi_level=wf_lvl, bat_info=bat_icon, serial_link=lnk, web_active=web_on)
        return bat

    def _sync(force=True):
        nid, sel = stack[-1]
        crumb = " > ".join([_title(f[0]) for f in stack])
        its = _items(nid)
        sel = max(0, min(sel, max(0, len(its) - 1)))
        stack[-1][1] = sel
        ui.clear_widgets(); ui.add_widget(sb); ui.add_widget(lm); ui.add_widget(fb); ui.set_focus(lm)
        _update_sb(crumb)
        lm.title = _title(nid).upper(); lm.set_items(its, selected=sel)
        fb.update(status=status_msg or crumb, status_kind=status_kind, hints=hints)
        ui.render(force=force)

    _sync(force=True); board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

    try:
        while stack:
            k = poll_fn() if poll_fn else None
            if not k:
                menu_ticks += 1
                if menu_ticks >= 20:
                    menu_ticks = 0
                    bat = board.get_battery()
                    if bat.get("charging") and bat.get("percent", 0) < 100:
                        chg_phase = (chg_phase + 1) & 3
                        crumb = " > ".join([_title(f[0]) for f in stack])
                        _update_sb(crumb)
                        ui.render(force=False)
                try:
                    import sys
                    _w = sys.modules.get("__pinhos_wdt__")
                    if _w is not None:
                        _w.feed()
                    m = sys.modules.get("main") or sys.modules.get("_pinhos_main")
                    if m and getattr(m, "runtime_state", {}).get("web_active") and hasattr(m, "step_webportal"):
                        m.step_webportal(20)
                        continue
                except Exception:
                    pass
                _sleep_ms(30); continue
            ku = str(k).upper()
            try:
                from boards.base import MOD_CTRL
                ctrl = bool(board.get_modifiers() & MOD_CTRL)
            except Exception:
                ctrl = False
            if (ctrl and ku == "P") or getattr(board, "pending_screenshot", None):
                _, smsg = show_screenshot_toast(board, ui, fb)
                if smsg:
                    status_msg, status_kind = smsg, "ok"
                continue
            if ctrl and ku == "Q":
                try:
                    import sys
                    m = sys.modules.get("main")
                    if m and hasattr(m, "toggle_serial_link"):
                        on, smsg = m.toggle_serial_link(board, logger)
                        status_msg, status_kind = smsg, ("ok" if on else "info")
                        _sync(force=True)
                except Exception:
                    pass
                continue
            if ku in ("ESC", "BACK", "BACKSPACE"):
                board.beep(900, 10); stack.pop(); status_msg, status_kind = "", "info"
                if stack:
                    _sync(force=True)
                continue
            if ku in ("UP", "DOWN"):
                if ui.handle_key(ku, allow_hotkeys=False):
                    stack[-1][1] = lm.selected; board.beep(1100, 8); ui.render(force=False)
                continue
            if ku in ("ENTER", "SPACE", " "):
                it = lm.get_selected_item()
                if not isinstance(it, dict) or not it.get("id"):
                    continue
                aid = it["id"]; stack[-1][1] = lm.selected; board.beep(1350, 12)
                if aid.startswith("cat:"):
                    stack.append([aid[4:], 0]); status_msg, status_kind = "", "info"; _sync(force=True)
                elif aid.startswith("tool:") and aid[5:] in TOOL_MAP:
                    p, lbl, wt = TOOL_MAP[aid[5:]]
                    status_msg, status_kind = run_tool_cb(p, lbl, wt); _sync(force=True)
                elif aid.startswith("app:"):
                    ap = aid[4:]
                    status_msg, status_kind = run_tool_cb(ap, it.get("label", "App"), ap.endswith("hello_world.py")); _sync(force=True)
                elif aid.startswith("theme:"):
                    t = theme_mgr.apply(aid[6:], persist=True)
                    status_msg, status_kind = "Theme: " + t.name, "ok"; _sync(force=True)
                elif aid == "set:mode":
                    ui.toggle_mode(persist=True)
                    status_msg, status_kind = "UI Mode: " + ui.mode_badge, "ok"; _sync(force=True)
                elif aid == "set:layout":
                    cur = str(cfg.get("launcher_layout", "grid") if cfg else "grid").lower()
                    nxt = "list" if cur == "grid" else "grid"
                    if cfg:
                        cfg.set("launcher_layout", nxt, save_now=True)
                    status_msg, status_kind = "Layout: " + nxt.upper(), "ok"; _sync(force=True)
                elif aid == "set:boot_scr":
                    cur = str(cfg.get("boot_screen", "desktop") if cfg else "desktop").lower()
                    nxt = "drawer" if cur == "desktop" else "desktop"
                    if cfg:
                        cfg.set("boot_screen", nxt, save_now=True)
                    status_msg, status_kind = "Boot Screen: " + ("HOME" if nxt == "desktop" else "DRAWER"), "ok"; _sync(force=True)
                elif aid == "set:wifi_ind":
                    from net.wifi import WIFI_INDICATOR_MODES
                    cur = str(cfg.get("wifi_indicator", "bars") if cfg else "bars").lower()
                    idx = (WIFI_INDICATOR_MODES.index(cur) + 1) % len(WIFI_INDICATOR_MODES) if cur in WIFI_INDICATOR_MODES else 0
                    nxt = WIFI_INDICATOR_MODES[idx]
                    if cfg:
                        cfg.set("wifi_indicator", nxt, save_now=True)
                    status_msg, status_kind = "Wi-Fi Bar: " + nxt.upper().replace("_", "+"), "ok"; _sync(force=True)
                elif aid == "set:bat_ind":
                    modes = ("both", "icon", "pct", "off")
                    cur = str(cfg.get("battery_indicator", "both") if cfg else "both").lower()
                    nxt = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "both"
                    if cfg:
                        cfg.set("battery_indicator", nxt, save_now=True)
                    status_msg, status_kind = "Battery Bar: " + nxt.upper(), "ok"; _sync(force=True)
                elif aid == "set:sound":
                    cur = bool(cfg.get("sound", True) if cfg else True)
                    nxt = not cur
                    if cfg:
                        cfg.set("sound", nxt, save_now=True)
                    if hasattr(board, "config") and isinstance(board.config, dict):
                        board.config["sound"] = nxt
                    status_msg, status_kind = "Key Sound: " + ("ON" if nxt else "OFF"), "ok"; _sync(force=True)
                elif aid == "set:lcd_bl":
                    cur = board.get_backlight(); nv = 10 if cur >= 100 else min(100, ((cur // 10) + 1) * 10)
                    board.set_backlight(nv)
                    if cfg:
                        cfg.set("lcd_brightness", nv, save_now=True)
                    status_msg, status_kind = "LCD Backlight: {}%".format(nv), "ok"; _sync(force=True)
                elif aid == "set:kb_bl":
                    cur = board.get_kb_backlight(); nv = 0 if cur >= 100 else min(100, ((cur // 10) + 1) * 10)
                    board.set_kb_backlight(nv)
                    if cfg:
                        cfg.set("kb_brightness", nv, save_now=True)
                    status_msg, status_kind = "KB Backlight: {}%".format(nv), "ok"; _sync(force=True)
                elif aid == "info:bat_rtc":
                    b = board.get_battery()
                    show_info_dialog(board, ui, "BATTERY & RTC", [
                        "Battery : {}% ({}mV)".format(b["percent"], b["voltage_mv"]),
                        "State   : {}".format("CHARGING" if b["charging"] else "On Battery"),
                        "RTC     : " + board.get_timestamp_str(),
                        "Die Temp: {}C".format(board.get_cpu_temp_c()),
                    ]); _sync(force=True)
                elif aid == "info:version":
                    show_info_dialog(board, ui, "ABOUT PINHOS", [
                        "OS Ver  : v{}".format(manifest.get("version", "1.0.0-alpha.4.4")),
                        "UF2 Fw  : {}".format(manifest.get("firmware_version", "?")),
                        "Arch/MCU: {} / {}".format(manifest.get("arch", "?"), manifest.get("mcu", "RP2350")),
                        "Build   : {}".format(manifest.get("build_id", "?")),
                    ]); _sync(force=True)
                elif aid == "info:board":
                    gc.collect()
                    fk = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
                    uk = (gc.mem_alloc() // 1024) if hasattr(gc, "mem_alloc") else 64
                    sd = board.get_sd_stats()
                    devs = board.i2c_scan() if hasattr(board, "i2c_scan") else []
                    show_info_dialog(board, ui, "BOARD & SRAM", [
                        "Board : " + board.name[:32],
                        "SRAM  : {}KB free / {}KB used".format(fk, uk),
                        "SD    : {}MB free".format(sd["free_kb"] // 1024) if sd.get("mounted") else "SD    : Unmounted",
                        "I2C   : {}".format(" ".join(["0x{:02x}".format(d) for d in devs]) or "none"),
                    ]); _sync(force=True)
                elif aid == "act:logs":
                    open_log_viewer(board, ui, logger, kind="system"); _sync(force=True)
                elif aid == "act:selftest":
                    import tests.selftest as _st
                    res = _st.run_all(interactive_wait=True)
                    board.set_lut(theme_mgr.active.lut)
                    status_msg = "Self-Test {}/{} {}".format(res.get("passed", 0), res.get("total", 10), "PASS" if res.get("ok") else "FAIL")
                    status_kind = "ok" if res.get("ok") else "err"; _sync(force=True)
                elif aid == "act:reboot":
                    if confirm_dialog(board, ui, "REBOOT PINHOS?", ["Write clean breadcrumb and", "perform hardware reset?"]):
                        try:
                            from core.config import save_rtc_state
                            save_rtc_state(board)
                        except Exception:
                            pass
                        if logger:
                            logger.info("UI: Clean reboot"); logger.clear_breadcrumb("CLEAN_EXIT")
                        import machine; machine.reset()
                    _sync(force=True)
                elif aid == "wifi:status":
                    from net.wifi import get_wifi_manager
                    st = get_wifi_manager().status()
                    show_info_dialog(board, ui, "WI-FI STATUS", [
                        "State : {}".format("CONNECTED" if st["connected"] else ("ON (Idle)" if st["active"] else "OFF")),
                        "SSID  : {}".format(st["ssid"] or "(none)"),
                        "IP    : {}".format(st["ip"]),
                        "GW/Sig: {} | {}dBm".format(st["gw"], st["rssi"]),
                    ]); _sync(force=True)
                elif aid == "wifi:scan":
                    status_msg, status_kind = _wifi_scan_and_connect(board, ui, sb, lm, fb, cfg=cfg); _sync(force=True)
                elif aid == "wifi:saved":
                    status_msg, status_kind = _wifi_saved_menu(board, ui, sb, lm, fb, cfg=cfg); _sync(force=True)
                elif aid == "wifi:auto":
                    from net.wifi import get_wifi_manager
                    wm = get_wifi_manager()
                    nxt = not wm.get_auto_connect()
                    wm.set_auto_connect(nxt)
                    status_msg, status_kind = "Auto-Connect: " + ("ON" if nxt else "OFF"), "ok"; _sync(force=True)
                elif aid == "wifi:country":
                    import sys
                    gc.collect()
                    import ui._menu_net as _mn
                    try:
                        cc = _mn.wifi_prompt_country(board, ui, fb, cfg=cfg)
                    finally:
                        _mn = None
                        sys.modules.pop("ui._menu_net", None)
                        gc.collect()
                    status_msg = ("Wi-Fi Country: " + cc) if cc else "Country unchanged"
                    status_kind = "ok" if cc else "info"
                    _sync(force=True)
                elif aid == "ntp:sync":
                    from net.wifi import get_wifi_manager, sync_ntp
                    st_wf = get_wifi_manager().status()
                    if not st_wf.get("connected") or str(st_wf.get("ip", "0.0.0.0")) in ("0.0.0.0", "N/A", "ERR", ""):
                        status_msg, status_kind = "Wi-Fi offline (Scan & Connect first)", "warn"
                        _sync(force=True)
                        continue
                    fb.update(status="Syncing RTC via NTP (ESC:Cancel)...", status_kind="warn"); ui.render(force=False)
                    tz = int(cfg.get("tz_offset_h", 0) if cfg else 0)
                    host = str(cfg.get("ntp_server", "162.159.200.1") if cfg else "162.159.200.1")
                    ok, msg = sync_ntp(
                        board=board,
                        tz_offset_h=tz,
                        host=host,
                        timeout_s=5,
                        cancel_cb=lambda: (poll_fn() if poll_fn else None) in ("ESC", "Q", "BACK", "BACKSPACE"),
                        status_cb=lambda ph: (fb.update(status=ph, status_kind="warn"), ui.render(force=False)),
                    )
                    if ok:
                        try:
                            from core.config import save_rtc_state
                            save_rtc_state(board)
                        except Exception:
                            pass
                    status_msg, status_kind = msg, ("ok" if ok else "err"); _sync(force=True)
                elif aid == "ntp:auto":
                    cur = bool(cfg.get("ntp_auto", True) if cfg else True)
                    nxt = not cur
                    if cfg:
                        cfg.set("ntp_auto", nxt, save_now=True)
                    status_msg, status_kind = "Auto-NTP: " + ("ON" if nxt else "OFF"), "ok"; _sync(force=True)
                elif aid == "ntp:resync":
                    opts = (0, 1800, 3600, 10800, 21600)
                    cur = int(cfg.get("ntp_resync_s", 3600) if cfg else 3600)
                    nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 3600
                    if cfg:
                        cfg.set("ntp_resync_s", nxt, save_now=True)
                    lbl = "OFF" if nxt <= 0 else ("{}h".format(nxt // 3600) if nxt >= 3600 else "{}m".format(nxt // 60))
                    status_msg, status_kind = "NTP Resync: " + lbl, "ok"; _sync(force=True)
                elif aid == "ntp:tz":
                    cur = int(cfg.get("tz_offset_h", 0) if cfg else 0)
                    nxt = -12 if cur >= 14 else (cur + 1)
                    if cfg:
                        cfg.set("tz_offset_h", nxt, save_now=True)
                    status_msg, status_kind = "Timezone: UTC{}{}".format("+" if nxt >= 0 else "", nxt), "ok"; _sync(force=True)
                elif aid == "rtc:date":
                    dt = board.get_rtc_datetime()
                    cur_s = "{:04d}-{:02d}-{:02d}".format(dt[0], dt[1], dt[2])
                    val = _prompt_line(board, ui, fb, "DATE(Y-M-D)", cur_s, allowed="0123456789-", max_len=10)
                    if val is not None:
                        try:
                            yr, mo, dy = [int(x) for x in val.split("-")]
                            if 2020 <= yr <= 2099 and 1 <= mo <= 12 and 1 <= dy <= 31:
                                board.set_rtc_datetime((yr, mo, dy, dt[3], dt[4], dt[5], dt[6], 0))
                                try:
                                    from core.config import save_rtc_state
                                    save_rtc_state(board)
                                except Exception:
                                    pass
                                status_msg, status_kind = "Date set: {:04d}-{:02d}-{:02d}".format(yr, mo, dy), "ok"
                            else:
                                status_msg, status_kind = "Invalid date range", "err"
                        except Exception:
                            status_msg, status_kind = "Use YYYY-MM-DD format", "err"
                    _sync(force=True)
                elif aid == "rtc:time":
                    dt = board.get_rtc_datetime()
                    cur_s = "{:02d}:{:02d}:{:02d}".format(dt[4], dt[5], dt[6])
                    val = _prompt_line(board, ui, fb, "TIME(H:M:S)", cur_s, allowed="0123456789:", max_len=8)
                    if val is not None:
                        try:
                            pts = [int(x) for x in val.split(":")]
                            hh, mm = pts[0], pts[1]
                            ss = pts[2] if len(pts) > 2 else 0
                            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                                board.set_rtc_datetime((dt[0], dt[1], dt[2], dt[3], hh, mm, ss, 0))
                                try:
                                    from core.config import save_rtc_state
                                    save_rtc_state(board)
                                except Exception:
                                    pass
                                status_msg, status_kind = "Time set: {:02d}:{:02d}:{:02d}".format(hh, mm, ss), "ok"
                            else:
                                status_msg, status_kind = "Invalid time range", "err"
                        except Exception:
                            status_msg, status_kind = "Use HH:MM or HH:MM:SS", "err"
                    _sync(force=True)
                elif aid == "cfg:save_snap":
                    if cfg and cfg.save_snapshot():
                        try:
                            os.remove("/sd/pinhos/config_snapshot.json")
                        except OSError:
                            pass
                        status_msg, status_kind = "Saved /sd/pinhos/config.snap.json", "ok"
                    else:
                        status_msg, status_kind = "Snapshot save failed", "err"
                    _sync(force=True)
                elif aid == "cfg:load_snap":
                    if not cfg or not cfg.has_snapshot():
                        status_msg, status_kind = "No config.snap.json on SD yet", "warn"
                    elif confirm_dialog(board, ui, "LOAD CONFIG SNAPSHOT?", ["Overwrite active config.json", "from /sd/pinhos/config.snap.json?"]):
                        ok, msg = cfg.load_snapshot(save_now=True)
                        if ok:
                            try:
                                os.remove("/sd/pinhos/config_snapshot.json")
                            except OSError:
                                pass
                            theme_mgr.apply(cfg.get("theme", "cyber_amber"), persist=False)
                            ui.set_mode(cfg.get("ui_mode", "gui"), persist=False)
                            board.set_backlight(cfg.get("lcd_brightness", 80))
                            board.set_kb_backlight(cfg.get("kb_brightness", 60))
                            if hasattr(board, "config") and isinstance(board.config, dict):
                                board.config["sound"] = bool(cfg.get("sound", True))
                            try:
                                import machine
                                machine.freq(int(cfg.get("cpu_freq_mhz", 150)) * 1000000)
                                if hasattr(board, "init_uart_bridge"):
                                    board.init_uart_bridge(rebind=True)
                            except Exception:
                                pass
                        status_msg, status_kind = msg, ("ok" if ok else "err")
                    _sync(force=True)
                elif aid == "sync:themes":
                    fb.update(status="Syncing themes from GitHub...", status_kind="warn"); ui.render(force=False)
                    try:
                        from net.sync import sync_themes
                        ok_n, sk_n = sync_themes(config=cfg, theme_mgr=theme_mgr,
                                                 progress_cb=lambda m: (fb.update(status=m, status_kind="info"), ui.render(force=False)))
                        status_msg, status_kind = "Themes synced: {} OK ({} skip)".format(ok_n, sk_n), "ok"
                    except Exception as e:
                        status_msg, status_kind = "Sync err: " + str(e)[:28], "err"
                    _sync(force=True)
                elif aid == "sync:apps":
                    fb.update(status="Syncing apps from GitHub...", status_kind="warn"); ui.render(force=False)
                    try:
                        from net.sync import sync_apps
                        ok_n, sk_n = sync_apps(config=cfg,
                                               progress_cb=lambda m: (fb.update(status=m, status_kind="info"), ui.render(force=False)))
                        status_msg, status_kind = "Apps synced: {} OK ({} skip)".format(ok_n, sk_n), "ok"
                    except Exception as e:
                        status_msg, status_kind = "Sync err: " + str(e)[:28], "err"
                    _sync(force=True)
                elif aid == "sync:check":
                    fb.update(status="Checking GitHub version.json...", status_kind="warn"); ui.render(force=False)
                    try:
                        from net.sync import check_remote_version
                        lv, rv, rp = check_remote_version(config=cfg)
                        show_info_dialog(board, ui, "GITHUB VERSION", [
                            "Repo   : " + rp[:30],
                            "Local  : v" + lv,
                            "Remote : v" + rv,
                            "Status : " + ("Up to date!" if lv == rv else "Update available"),
                        ])
                        status_msg, status_kind = "Remote: v" + rv, "ok"
                    except Exception as e:
                        status_msg, status_kind = "Check err: " + str(e)[:28], "err"
                    _sync(force=True)
                elif aid == "wifi:off":
                    from net.wifi import get_wifi_manager
                    get_wifi_manager().disconnect()
                    status_msg, status_kind = "Wi-Fi disconnected", "warn"; _sync(force=True)
                elif aid == "web:toggle":
                    return "TOGGLE_WEBPORTAL"
                elif aid == "web:info":
                    import sys as _sys
                    _mm = _sys.modules.get("main") or _sys.modules.get("_pinhos_main")
                    _rs = getattr(_mm, "runtime_state", {}) if _mm else {}
                    _ws = _rs.get("web_server")
                    if _ws is not None and getattr(_ws, "running", False):
                        try:
                            from web import portal_url
                            _url = portal_url(_ws.port)
                        except Exception:
                            _url = "http://0.0.0.0:{}".format(getattr(_ws, "port", 8080))
                        show_info_dialog(board, ui, "WEBPORTAL IDE TOKEN", [
                            "Status: ACTIVE",
                            "URL   : " + str(_url)[:28],
                            "Token : " + str(getattr(_ws, "token", "")),
                            "",
                            "Enter token in browser prompt",
                            "or X-PinhOS-Token header.",
                        ], kind="ok")
                    else:
                        show_info_dialog(board, ui, "WEBPORTAL IDE TOKEN", [
                            "Status: STOPPED",
                            "Enable 'WebPortal IDE' first",
                            "to generate a per-boot token.",
                        ], kind="info")
                    _sync(force=True)
                elif aid == "web:auto":
                    cur = bool(cfg.get("webportal_autostart", False) if cfg else False)
                    nxt = not cur
                    if cfg:
                        cfg.set("webportal_autostart", nxt, save_now=True)
                    status_msg, status_kind = "Auto-Start WebPortal: " + ("ON" if nxt else "OFF"), "ok"; _sync(force=True)
                elif aid == "set:sleep_to":
                    opts = (0, 60, 120, 300, 600)
                    cur = int(cfg.get("sleep_timeout_s", 300) if cfg else 300)
                    nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 300
                    if cfg:
                        cfg.set("sleep_timeout_s", nxt, save_now=True)
                    lbl = "OFF" if nxt <= 0 else "{} min".format(nxt // 60)
                    status_msg, status_kind = "Auto-Sleep: " + lbl, "ok"; _sync(force=True)
                elif aid == "set:swap_kb":
                    opts = (0, 128, 256, 512, 1024, 2048, 4096)
                    cur = int(cfg.get("swap_max_kb", 512) if cfg else 512)
                    nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 512
                    if cfg:
                        cfg.set("swap_max_kb", nxt, save_now=True)
                        cfg.set("swap_enabled", nxt > 0, save_now=True)
                    try:
                        from core.swap import get_swap_manager
                        get_swap_manager().set_max_kb(nxt)
                    except Exception:
                        pass
                    lbl = "OFF" if nxt <= 0 else ("{} MB".format(nxt // 1024) if nxt >= 1024 else "{} KB".format(nxt))
                    status_msg, status_kind = "SD Swap Quota: " + lbl, "ok"; _sync(force=True)
                elif aid == "act:swap_clr":
                    try:
                        from core.swap import get_swap_manager
                        n = get_swap_manager().clear_all()
                        status_msg, status_kind = "Cleared {} swap file(s)".format(n), "ok"
                    except Exception as e:
                        status_msg, status_kind = "Swap clear err: " + str(e)[:20], "err"
                    _sync(force=True)
                elif aid == "set:cpu_mhz":
                    opts = (100, 150, 200, 240, 250)
                    try:
                        import machine
                        cur = machine.freq() // 1000000
                    except Exception:
                        cur = int(cfg.get("cpu_freq_mhz", 150) if cfg else 150)
                    nxt = opts[0]
                    for v in opts:
                        if v > cur:
                            nxt = v
                            break
                    try:
                        import machine
                        machine.freq(nxt * 1000000)
                        if hasattr(board, "init_uart_bridge"):
                            board.init_uart_bridge(rebind=True)
                        if cfg:
                            cfg.set("cpu_freq_mhz", nxt, save_now=True)
                        tag = {100: "Eco", 150: "Stock", 200: "Fast", 240: "Turbo", 250: "Max"}.get(nxt, "")
                        status_msg, status_kind = "CPU Clock: {} MHz ({})".format(nxt, tag), "warn" if nxt > 150 else "ok"
                    except Exception as e:
                        status_msg, status_kind = "CPU Clock err: " + str(e)[:20], "err"
                    _sync(force=True)
                elif aid == "set:wdt_to":
                    opts = (8000, 6000, 4000, 0)
                    cur = int(cfg.get("wdt_timeout_ms", 8000) if cfg else 8000)
                    nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 8000
                    if cfg:
                        cfg.set("wdt_timeout_ms", nxt, save_now=True)
                    lbl = "OFF" if nxt <= 0 else "{}s (max 8.3s)".format(nxt // 1000)
                    status_msg, status_kind = "Watchdog: {} (next boot)".format(lbl), ("warn" if nxt <= 0 else "ok")
                    _sync(force=True)
                elif aid == "act:sleep":
                    return "SLEEP_NOW"
                elif aid == "act:repl":
                    try:
                        import sys
                        m = sys.modules.get("main")
                        if m and hasattr(m, "toggle_serial_link"):
                            on, smsg = m.toggle_serial_link(board, logger)
                            status_msg, status_kind = smsg, ("ok" if on else "info")
                        else:
                            status_msg, status_kind = "COM4 Serial Link active", "ok"
                    except Exception:
                        status_msg, status_kind = "COM4 Serial Link toggled", "ok"
                    _sync(force=True)
    except KeyboardInterrupt:
        pass
    gc.collect()
    return None

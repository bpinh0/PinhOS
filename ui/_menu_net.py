# PinhOS — On-Demand Wi-Fi Scan, Saved & Connect Dialogs (ui/_menu_net.py)
# Loaded lazily by ui/menu.py and purged on return to keep RP2350 peak SRAM low.

import gc
import time


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def is_valid_country_code(code):
    """Validate 2-letter ISO-3166 alpha-2 Wi-Fi regulatory code (rejects 'XX') (#27)."""
    s = str(code or "").strip().upper()
    if len(s) != 2 or s == "XX":
        return False
    return ("A" <= s[0] <= "Z") and ("A" <= s[1] <= "Z")


def wifi_prompt_country(board, ui, fb, cfg=None):
    """Prompt for 2-letter ISO-3166 Wi-Fi country code (e.g. US, GB, DE, PT), validate & persist (#27)."""
    cur = str(cfg.get("wifi_country", "XX") if cfg else "XX").strip().upper()
    buf = "" if cur == "XX" else cur[:2]
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    err_msg = ""
    while True:
        st_txt = err_msg if err_msg else "Wi-Fi Country (2-ltr e.g. US/GB): {}_".format(buf)
        fb.update(
            status=st_txt,
            status_kind="err" if err_msg else "info",
            hints="A-Z (2 chars) ENT:Save ESC:Skip",
        )
        ui.render(force=False)
        k = poll_fn() if poll_fn else None
        if k is None:
            _sleep_ms(30); continue
        err_msg = ""
        ku = str(k).upper()
        if ku in ("ESC", "BACK"):
            return None
        if ku in ("ENTER", "RETURN"):
            cc = buf.strip().upper()
            if not is_valid_country_code(cc):
                board.beep(700, 15)
                err_msg = "Invalid '{}': use 2 letters (not XX)".format(cc)
                continue
            if cfg is not None:
                cfg.set("wifi_country", cc, save_now=True)
            try:
                import network
                if hasattr(network, "country"):
                    network.country(cc)
            except Exception:
                pass
            board.beep(1450, 12)
            return cc
        if ku == "BACKSPACE":
            buf = buf[:-1]
        elif len(ku) == 1 and ("A" <= ku <= "Z") and len(buf) < 2:
            buf += ku


def ensure_wifi_country(board, ui, fb, cfg=None):
    """If wifi_country is still 'XX', prompt once during Wi-Fi setup (#27)."""
    if cfg is None:
        return None
    cur = str(cfg.get("wifi_country", "XX")).strip().upper()
    if is_valid_country_code(cur):
        return cur
    return wifi_prompt_country(board, ui, fb, cfg=cfg)


def wifi_prompt_password(board, ui, fb, ssid, initial=""):
    """Inline password prompt on FooterBar (TAB toggles mask, ENTER submits, ESC cancels)."""
    buf = str(initial)
    masked = True
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while True:
        shown = ("*" * len(buf)) if masked else buf
        fb.update(
            status="PW[{}]: {}_".format(ssid[:12], shown[-24:]),
            status_kind="info",
            hints="ENT:Connect TAB:Show/Hide ESC:Cancel",
        )
        ui.render(force=False)
        k = poll_fn() if poll_fn else None
        if k is None:
            _sleep_ms(30); continue
        if k == "ESC":
            return None
        if k == "ENTER":
            return buf
        if k == "TAB":
            masked = not masked
        elif k == "BACKSPACE":
            buf = buf[:-1]
        elif k == "SPACE":
            buf += " "
        elif len(k) == 1 and " " <= k <= "~":
            buf += k


def wifi_connect_dialog(board, ui, wm, ssid, pw, save=True, cfg=None):
    """Android-style modal Wi-Fi progress Dialog with live phase & timeout counter."""
    from ui.widgets import Dialog
    from net.wifi import sync_ntp

    dlg = Dialog(
        18, 76, 284, 152,
        title="WI-FI CONNECT",
        lines=[
            "Network : " + str(ssid)[:24],
            "Phase   : Initializing...",
            "Timeout : 00s / 24s",
            "Status  : Please wait...",
        ],
        footer="[ESC/BS] Cancel",
        kind="info",
    )
    ui.add_widget(dlg)
    ui.render(force=False)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

    def _is_cancel():
        if not poll_fn:
            return False
        k = poll_fn()
        return k is not None and str(k).upper() in ("ESC", "Q", "BACK", "BACKSPACE")

    def _on_phase(phase, el_s, lim_s, st_code):
        dlg.set_content(
            lines=[
                "Network : " + str(ssid)[:24],
                "Phase   : " + str(phase)[:24],
                "Timeout : {:02d}s / {:02d}s (st={})".format(int(el_s), int(lim_s), st_code),
                "Status  : Connecting...",
            ],
            kind="warn" if el_s >= 10 else "info",
        )
        ui.render(force=False)

    def _on_ntp_phase(nphase):
        dlg.set_content(
            lines=[
                "Network : " + str(ssid)[:24],
                "Phase   : " + str(nphase)[:24],
                "Timeout : Connected!",
                "Status  : " + str(msg)[:24],
            ],
            footer="[ESC/BS] Skip NTP",
            kind="ok",
        )
        ui.render(force=False)

    ok, msg = False, "Connect failed"
    try:
        ok, msg = wm.connect(
            ssid, pw, timeout_s=24,
            cancel_cb=_is_cancel,
            save=save,
            status_cb=_on_phase,
            max_attempts=3,
        )
        if ok and (cfg.get("ntp_auto", True) if cfg else True):
            try:
                import sys
                m = sys.modules.get("main")
                if m and isinstance(getattr(m, "runtime_state", None), dict):
                    m.runtime_state["ntp_pending"] = True
            except Exception:
                pass

        dlg.set_content(
            lines=[
                "Network : " + str(ssid)[:24],
                "Phase   : " + ("Connected!" if ok else "Failed"),
                "Status  : " + str(msg)[:24],
                "",
            ],
            footer="Returning...",
            kind="ok" if ok else "err",
        )
        ui.render(force=False)
        board.beep(1500 if ok else 700, 15)
        _sleep_ms(700)
    except Exception as e:
        msg = "Wi-Fi err: " + str(e)[:20]
        ok = False
    finally:
        ui.remove_widget(dlg)
        ui.mark_all_dirty(True)
        board.clear_input()
        ui.render(force=True)
    return msg, ("ok" if ok else "err")


def wifi_scan_and_connect(board, ui, sb, lm, fb, cfg=None):
    from net.wifi import get_wifi_manager
    ensure_wifi_country(board, ui, fb, cfg=cfg)
    wm = get_wifi_manager()
    fb.update(status="Scanning 2.4 GHz Wi-Fi...", status_kind="warn", hints="Please wait...")
    ui.render(force=False)
    aps = wm.scan()
    if not aps:
        return "No Wi-Fi networks found", "warn"
    items = [
        {"id": ap["ssid"], "label": ap["ssid"][:24], "badge": "{}dB".format(ap["rssi"])}
        for ap in aps[:16]
    ]
    sb.update(title="Settings > Wi-Fi > Scan", mode_label=ui.mode_badge)
    lm.title = "SELECT NETWORK ({})".format(len(items))
    lm.set_items(items, selected=0)
    fb.update(status="Pick SSID and press ENTER", status_kind="info", hints="UP/DN:Sel ENT:Join ESC:Back")
    ui.render(force=True)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while True:
        k = poll_fn() if poll_fn else None
        if k is None:
            _sleep_ms(30); continue
        ku = str(k).upper()
        if ku in ("ESC", "BACK", "BACKSPACE"):
            return "Wi-Fi scan closed", "info"
        if ku in ("UP", "DOWN"):
            if ui.handle_key(ku, allow_hotkeys=False):
                board.beep(1100, 8); ui.render(force=False)
        elif ku == "ENTER":
            it = lm.get_selected_item()
            if not it:
                continue
            ssid = it["id"]
            saved_pw = wm.get_saved_password(ssid)
            pw = wifi_prompt_password(board, ui, fb, ssid, initial=saved_pw)
            if pw is None:
                return "Cancelled", "info"
            return wifi_connect_dialog(board, ui, wm, ssid, pw, save=True, cfg=cfg)


def wifi_saved_menu(board, ui, sb, lm, fb, cfg=None):
    from net.wifi import get_wifi_manager
    wm = get_wifi_manager()
    nets = wm.list_saved()
    if not nets:
        return "No saved Wi-Fi networks", "info"
    items = [{"id": n["ssid"], "pw": n.get("password", ""), "label": n["ssid"][:26], "badge": "[SAVED]"} for n in nets]
    sb.update(title="Settings > Wi-Fi > Saved", mode_label=ui.mode_badge)
    lm.title = "SAVED NETWORKS"
    lm.set_items(items, selected=0)
    fb.update(status="ENT:Connect  D:Forget  ESC:Back", status_kind="info", hints="UP/DN:Sel ENT:Join D:Forget ESC")
    ui.render(force=True)
    board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while True:
        k = poll_fn() if poll_fn else None
        if k is None:
            _sleep_ms(30); continue
        ku = str(k).upper()
        if ku in ("ESC", "BACK", "BACKSPACE"):
            return "Closed saved list", "info"
        if ku in ("UP", "DOWN"):
            if ui.handle_key(ku, allow_hotkeys=False):
                ui.render(force=False)
        elif ku == "D":
            it = lm.get_selected_item()
            if it:
                wm.forget_network(it["id"])
                return "Forgot " + it["id"], "warn"
        elif ku == "ENTER":
            it = lm.get_selected_item()
            if it:
                ensure_wifi_country(board, ui, fb, cfg=cfg)
                return wifi_connect_dialog(board, ui, wm, it["id"], it["pw"], save=False, cfg=cfg)

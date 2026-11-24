# PinhOS Phase 3 — Network Field Probes (tools/net_tools.py)
# Wi-Fi status, DNS resolver, TCP RTT ping, fast TCP port scanner, local subnet sweep,
# and Wake-on-LAN (WoL) magic packet sender. Short timeouts; safe when offline.
# Zero full-screen framebuffers; zero hardcoded GPIO pins.

APP_META = {
    "id": "net_tools",
    "name": "Network Probes",
    "version": "1.0.0",
    "category": "Network",
    "description": "DNS resolver, TCP RTT ping, port scanner, subnet sweep & Wake-on-LAN",
    "entry": "main",
    "min_sram": 40960,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}

import gc
import socket
import time


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else (a - b)


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def get_wifi_status():
    """Read CYW43439 Wi-Fi STA status cleanly without modifying radio state."""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        active = bool(wlan.active())
        conn = bool(wlan.isconnected()) if active else False
        if conn:
            ip, mask, gw, dns = wlan.ifconfig()
            return {"active": True, "connected": True, "ip": ip, "mask": mask, "gw": gw, "dns": dns}
        return {"active": active, "connected": False, "ip": "0.0.0.0", "gw": "0.0.0.0", "dns": "0.0.0.0"}
    except Exception:
        return {"active": False, "connected": False, "ip": "N/A", "gw": "N/A", "dns": "N/A"}


def build_wol_packet(mac_str):
    """Build a 102-byte Wake-on-LAN magic packet from 'AA:BB:CC:DD:EE:FF' or 'AA-BB-...'."""
    cleaned = str(mac_str).strip().replace("-", ":").replace(".", ":")
    parts = [p for p in cleaned.split(":") if p]
    if len(parts) != 6:
        raise ValueError("MAC must have 6 octets (AA:BB:CC:DD:EE:FF)")
    mac_bytes = bytes([int(p, 16) for p in parts])
    return (b"\xff" * 6) + (mac_bytes * 16)


def send_wol(mac_str, bcast="255.255.255.255", port=9):
    pkt = build_wol_packet(mac_str)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass
        s.sendto(pkt, (bcast, int(port)))
        return len(pkt)
    finally:
        s.close()


def dns_lookup(host):
    t0 = _ticks_ms()
    info = socket.getaddrinfo(host, 80)
    dt = _ticks_diff(_ticks_ms(), t0)
    ips = []
    for item in info:
        ip = item[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips, dt


def tcp_probe(host, port, timeout_s=0.6):
    """Measure TCP connect RTT in ms. Returns (open_bool, rtt_ms, err_str)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout_s)
        t0 = _ticks_ms()
        addr = socket.getaddrinfo(host, int(port))[0][-1]
        s.connect(addr)
        dt = _ticks_diff(_ticks_ms(), t0)
        return True, dt, ""
    except Exception as e:
        return False, 0, str(e)
    finally:
        try:
            s.close()
        except Exception:
            pass


def _prompt(board, ui, fb, label, default=""):
    buf = str(default)
    board.clear_input()
    while True:
        fb.update(status="{}: {}_".format(label, buf[-34:]), status_kind="info", hints="ENTER:Run  ESC:Cancel")
        ui.render(force=False)
        k = board.poll_key()
        if k is None:
            _sleep_ms(30)
            continue
        if getattr(board, "pending_screenshot", None):
            from ui.menu import show_screenshot_toast
            show_screenshot_toast(board, ui, fb)
            continue
        if k == "ESC":
            return None
        if k == "ENTER":
            return buf.strip() or default
        if k == "BACKSPACE":
            buf = buf[:-1]
        elif k == "SPACE":
            buf += " "
        elif len(k) == 1 and " " <= k <= "~":
            buf += k


def main(ctx):
    board, ui = ctx.board, ctx.ui
    if board is None or ui is None:
        return {"error": "no board/ui"}

    from ui.widgets import StatusBar, ListMenu, TextView, FooterBar

    actions = [
        {"id": "status", "label": "1. Wi-Fi & IP Interface", "badge": "[1]"},
        {"id": "ping", "label": "2. TCP RTT Ping (4x)", "badge": "[2]"},
        {"id": "ports", "label": "3. TCP Port Scanner", "badge": "[3]"},
        {"id": "dns", "label": "4. DNS Resolver", "badge": "[4]"},
        {"id": "sweep", "label": "5. Subnet Host Sweep", "badge": "[5]"},
        {"id": "wol", "label": "6. Wake-on-LAN Magic Pkt", "badge": "[6]"},
    ]
    hints = "UP/DN:Sel ENT:Run M:Mode T:Theme ESC:Back"
    sb = StatusBar(0, 0, 320, 20, title="Net Probes", mode_label=ui.mode_badge)
    menu = ListMenu(4, 23, 312, 126, title="FIELD NETWORK TOOLS", items=actions)
    tv = TextView(4, 152, 312, 121, title="PROBE OUTPUT", lines=["Select a probe and press ENTER."])
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=hints)

    def sync_hdr(msg="Ready", kind="info"):
        st = get_wifi_status()
        sb.update(title="Net Probes", mode_label=ui.mode_badge, right_text=st["ip"][:15])
        fb.update(status=msg, status_kind=kind, hints=hints)

    def set_out(title, lines, msg="Done", kind="ok"):
        tv.title = title
        tv.set_lines(lines, reset_scroll=True)
        sync_hdr(msg, kind)
        ui.render(force=True)

    ui.clear_widgets()
    ui.add_widget(sb); ui.add_widget(menu); ui.add_widget(tv); ui.add_widget(fb)
    ui.set_focus(menu)
    sync_hdr("Offline (Phase 5 Wi-Fi Mgr)" if not get_wifi_status()["connected"] else "Wi-Fi Connected")
    ui.render(force=True)
    board.clear_input()

    try:
        while True:
            k = board.poll_key()
            if k is None:
                _sleep_ms(30)
                continue
            ku = k.upper()
            try:
                from boards.base import MOD_CTRL
                ctrl = bool(board.get_modifiers() & MOD_CTRL)
            except Exception:
                ctrl = False
            if (ctrl and ku == "P") or getattr(board, "pending_screenshot", None):
                from ui.menu import show_screenshot_toast
                _, smsg = show_screenshot_toast(board, ui, fb)
                if smsg:
                    sync_hdr(smsg, "ok")
                    ui.render(force=True)
                continue
            if ku in ("ESC", "Q"):
                break
            elif ku in ("UP", "DOWN"):
                if ui.handle_key(ku, allow_hotkeys=False):
                    ui.render(force=False)
            elif ku in ("M", "TAB"):
                ui.toggle_mode(persist=True); sync_hdr("Mode: " + ui.mode_badge); ui.render(force=True)
            elif ku == "T":
                ui.cycle_theme(step=1, persist=True); sync_hdr("Theme: " + ui.theme.name); ui.render(force=True)
            elif ku in ("ENTER", "1", "2", "3", "4", "5", "6"):
                if ku in "123456":
                    menu.set_selected(int(ku) - 1)
                act = menu.get_selected_item()["id"]
                st = get_wifi_status()
                if act == "status":
                    lines = [
                        "STA Active : {}".format("YES" if st["active"] else "NO"),
                        "Connected  : {}".format("YES" if st["connected"] else "NO"),
                        "IP Address : {}".format(st["ip"]),
                        "Gateway    : {}".format(st["gw"]),
                        "DNS Server : {}".format(st["dns"]),
                    ]
                    set_out("INTERFACE", lines, "Interface status refreshed")
                elif act == "dns":
                    host = _prompt(board, ui, fb, "Host", "example.com")
                    if host:
                        try:
                            ips, dt = dns_lookup(host)
                            set_out("DNS: " + host[:20], ["{} ({}ms)".format(ip, dt) for ip in ips], "Resolved OK")
                        except Exception as e:
                            set_out("DNS ERR", [str(e)], "DNS failed (check Wi-Fi)", "err")
                elif act == "ping":
                    default_gw = st["gw"] if st["connected"] and st["gw"] != "0.0.0.0" else "1.1.1.1"
                    host = _prompt(board, ui, fb, "Ping host", default_gw)
                    if host:
                        out, rtts = [], []
                        for seq in range(1, 5):
                            ok, dt, err = tcp_probe(host, 80, 0.8)
                            if ok:
                                rtts.append(dt)
                                out.append("seq={} {}:80 OK {}ms".format(seq, host, dt))
                            else:
                                out.append("seq={} {}:80 FAIL".format(seq, host))
                            tv.set_lines(out); ui.render(force=False)
                            if board.poll_key() == "ESC":
                                break
                        if rtts:
                            out.append("min={} avg={} max={}ms".format(min(rtts), sum(rtts) // len(rtts), max(rtts)))
                        set_out("TCP PING", out, "{}/4 replies".format(len(rtts)), "ok" if rtts else "warn")
                elif act == "ports":
                    default_gw = st["gw"] if st["connected"] and st["gw"] != "0.0.0.0" else "192.168.1.1"
                    host = _prompt(board, ui, fb, "Target IP", default_gw)
                    if host:
                        common = (22, 53, 80, 443, 8080, 1883, 3389)
                        out = []
                        for p in common:
                            if hasattr(ctx, "yield_"):
                                ctx.yield_()
                            ok, dt, _e = tcp_probe(host, p, 0.35)
                            out.append("port {:>4}: {}".format(p, "OPEN ({}ms)".format(dt) if ok else "closed"))
                            tv.set_lines(out); ui.render(force=False)
                            if board.poll_key() == "ESC":
                                break
                        set_out("PORTS " + host[:16], out, "Port scan complete")
                elif act == "sweep":
                    if not st["connected"]:
                        set_out("SUBNET SWEEP", ["Wi-Fi not connected.", "Connect STA first (Phase 5)."], "Offline", "warn")
                    else:
                        base = ".".join(st["ip"].split(".")[:3]) + "."
                        out = ["Scanning {}1..16 (port 80/22)...".format(base)]
                        for last in range(1, 17):
                            if hasattr(ctx, "yield_"):
                                ctx.yield_()
                            ip = base + str(last)
                            ok, dt, _e = tcp_probe(ip, 80, 0.15)
                            if ok:
                                out.append("UP {} ({}ms)".format(ip, dt))
                            if board.poll_key() == "ESC":
                                out.append("(aborted)"); break
                        set_out("SUBNET SWEEP", out, "Sweep done")
                elif act == "wol":
                    mac = _prompt(board, ui, fb, "MAC", "AA:BB:CC:DD:EE:FF")
                    if mac:
                        try:
                            n = send_wol(mac)
                            set_out("WAKE-ON-LAN", ["Sent {}B magic packet".format(n), "Target: " + mac], "WoL sent")
                        except Exception as e:
                            set_out("WOL ERR", [str(e)], "WoL failed", "err")
                gc.collect()
        return {"ok": True}
    finally:
        ui.clear_widgets()
        gc.collect()

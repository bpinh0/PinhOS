# PinhOS Phase 4 — WebPortal Browser IDE package & lifecycle helpers
import gc
import sys

__all__ = ["portal_url", "start_portal", "stop_portal", "toggle_portal", "step_portal"]


def portal_url(port=8080):
    ip = "127.0.0.1"
    try:
        from net.wifi import get_wifi_manager
        st = get_wifi_manager().status()
        if st and st.get("connected") and st.get("ip") not in ("0.0.0.0", "N/A", "ERR", ""):
            ip = str(st["ip"])
    except Exception:
        pass
    return "http://{}:{}".format(ip, int(port))


def start_portal(rs, board=None, cfg=None, logger=None, host="0.0.0.0", port=None):
    board = board or rs.get("board")
    cfg = cfg or rs.get("config")
    logger = logger or rs.get("logger")
    ws = rs.get("web_server")
    if ws is not None and ws.running:
        rs["web_active"] = True
        return True, "{} (Tok:{})".format(portal_url(ws.port), getattr(ws, "token", ""))
    p = int(port if port is not None else (cfg.get("webportal_port", 8080) if cfg else 8080))
    try:
        gc.collect()
        from web.server import WebServer
        ws = WebServer(board=board, config=cfg, manifest=rs.get("manifest"), logger=logger, host=host, port=p)
        ws.start()
        rs["web_server"] = ws
        rs["web_active"] = True
        return True, "{} (Tok:{})".format(portal_url(p), ws.token)
    except Exception as e:
        rs["web_server"] = None
        rs["web_active"] = False
        return False, "WebPortal err: " + str(e)[:26]


def stop_portal(rs):
    ws = rs.get("web_server")
    rs["web_server"] = None
    rs["web_active"] = False
    if ws is not None:
        try:
            ws.stop()
        except Exception:
            pass
        ws = None
    sys.modules.pop("web.server", None)
    gc.collect()
    return True, "WebPortal IDE stopped"


def toggle_portal(rs, board=None, cfg=None, logger=None):
    if rs.get("web_active"):
        stop_portal(rs)
        if board:
            board.beep(950, 12)
        return False, "WebPortal IDE stopped"
    ok, msg = start_portal(rs, board=board, cfg=cfg, logger=logger)
    if board:
        board.beep(1500 if ok else 700, 12)
    return ok, msg


def step_portal(rs, ms=15):
    ws = rs.get("web_server")
    if ws is not None and ws.running:
        try:
            ws.step(ms)
            return True
        except Exception:
            pass
    return False

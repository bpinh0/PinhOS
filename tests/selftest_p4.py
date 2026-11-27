# PinhOS Phase 4 — Gate 12 WebPortal Loopback & SRAM Self-Test (tests/selftest_p4.py)
import os, gc, json
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio


def _assert(c, m):
    if not c:
        raise AssertionError(m)


class _MemR:
    def __init__(self, d):
        self._b = d if isinstance(d, (bytes, bytearray)) else d.encode("utf-8")
        self._p = 0
    async def readline(self):
        if self._p >= len(self._b): return b""
        nl = self._b.find(b"\n", self._p)
        e = len(self._b) if nl < 0 else nl + 1
        o = self._b[self._p:e]; self._p = e; return o
    async def read(self, n=-1):
        if self._p >= len(self._b): return b""
        e = len(self._b) if (n is None or n < 0) else self._p + n
        o = self._b[self._p:e]; self._p = min(len(self._b), e); return o


class _MemW:
    def __init__(self):
        self.c = []; self.closed = False
    def write(self, d):
        self.c.append(bytes(d))
    async def drain(self):
        await (asyncio.sleep_ms(0) if hasattr(asyncio, "sleep_ms") else asyncio.sleep(0))
    def close(self):
        self.closed = True
    async def wait_closed(self):
        self.closed = True


async def _req_tcp(host, port, m, tgt, body=None):
    r, w = await asyncio.wait_for(asyncio.open_connection(host, port), 3)
    try:
        bb = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        w.write("{} {} HTTP/1.1\r\nHost: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(m, tgt, host, len(bb)).encode("utf-8"))
        if bb: w.write(bb)
        await w.drain()
        sl = (await asyncio.wait_for(r.readline(), 3)).decode("utf-8", "ignore").split()
        code = int(sl[1]) if len(sl) >= 2 else 0
        cl = -1
        for _ in range(24):
            hl = await asyncio.wait_for(r.readline(), 3)
            if not hl or hl in (b"\r\n", b"\n"): break
            hs = hl.decode("utf-8", "ignore")
            if hs.lower().startswith("content-length:"):
                cl = int(hs.split(":", 1)[1].strip())
        out = []
        while cl != 0:
            c = await asyncio.wait_for(r.read(min(512, cl) if cl > 0 else 512), 3)
            if not c: break
            out.append(c)
            if cl > 0: cl -= len(c)
        return code, b"".join(out)
    finally:
        try:
            w.close()
            if hasattr(w, "wait_closed"): await w.wait_closed()
        except Exception: pass


async def _req_pipe(ws, m, tgt, body=None, collect_body=True, hdrs=None):
    try:
        import sys as _sy
        _wd = _sy.modules.get("__pinhos_wdt__")
        if _wd is not None:
            _wd.feed()
    except Exception:
        pass
    bb = body.encode("utf-8") if isinstance(body, str) else (body or b"")
    ex = ""
    if hdrs:
        for k, v in hdrs.items():
            ex += "{}: {}\r\n".format(k, v)
    raw = "{} {} HTTP/1.1\r\nHost: 127.0.0.1\r\n{}Content-Length: {}\r\nConnection: close\r\n\r\n".format(m, tgt, ex, len(bb)).encode("utf-8") + bb
    wr = _MemW()
    await ws._handle_client(_MemR(raw), wr)
    _assert(wr.closed, "writer not closed")
    first = wr.c[0] if wr.c else b""
    fl = first.split(b"\r\n", 1)[0].decode("utf-8", "ignore").split()
    code = int(fl[1]) if len(fl) >= 2 else 0
    if not collect_body:
        has_pinhos = any(b"PinhOS" in ch for ch in wr.c)
        wr.c.clear()
        return code, (b"PinhOS" if has_pinhos else b"")
    buf = b"".join(wr.c)
    wr.c.clear()
    sep = buf.find(b"\r\n\r\n")
    return code, (buf[sep + 4:] if sep > 0 else b"")


def test_webportal_loopback(root="/sd/pinhos"):
    from boards import get_board
    from core.config import load_version_manifest
    from web.server import WebServer

    board = get_board()
    board.ensure_serial_repl()
    manifest = load_version_manifest(root=root)
    rel = "apps/_gate12_web.txt"
    full = root.rstrip("/") + "/" + rel
    txt = "PinhOS Phase 4 WebPortal Loopback OK!"
    mode = ["pipe"]

    async def _run():
        ws = WebServer(board=board, manifest=manifest, root=root, host="0.0.0.0", port=8080)
        await ws.start_async()
        _assert(len(ws.token) == 16 and ws.token != "pinhos01", "token entropy check failed")
        tok_h = {"X-PinhOS-Token": ws.token}
        try:
            c1, b1 = await _req_pipe(ws, "GET", "/", collect_body=False)
            _assert(c1 == 200 and b"PinhOS" in b1, "GET / fail: {}".format(c1))
            # Read-side auth + sensitive file denylist checks (Refs #23)
            c_wf0, _ = await _req_pipe(ws, "GET", "/api/file?path=wifi.json")
            _assert(c_wf0 == 401, "unauth GET wifi.json should 401, got {}".format(c_wf0))
            c_wf1, _ = await _req_pipe(ws, "GET", "/api/file?path=wifi.json", hdrs=tok_h)
            _assert(c_wf1 == 403, "auth GET wifi.json should 403 denylist, got {}".format(c_wf1))
            c_ls0, _ = await _req_pipe(ws, "GET", "/api/files")
            _assert(c_ls0 == 401, "unauth GET /api/files should 401, got {}".format(c_ls0))
            c2, b2 = await _req_pipe(ws, "GET", "/api/status", hdrs=tok_h)
            st = json.loads(b2.decode("utf-8"))
            _assert(c2 == 200 and st.get("ok") and "sram_free" in st and "sram_largest" in st and st.get("root") == root.rstrip("/"), "status fail")
            # Auth, CORS Origin, and write-allowlist security checks
            c_noauth, _ = await _req_pipe(ws, "POST", "/api/file?path=" + rel, txt)
            _assert(c_noauth == 401, "missing token should 401, got {}".format(c_noauth))
            c_cors, _ = await _req_pipe(ws, "POST", "/api/file?path=" + rel, txt, hdrs={"X-PinhOS-Token": ws.token, "Origin": "http://evil.example"})
            _assert(c_cors == 403, "cross-origin should 403, got {}".format(c_cors))
            c_deny, _ = await _req_pipe(ws, "POST", "/api/file?path=core/config.py", txt, hdrs=tok_h)
            _assert(c_deny == 403, "core write should 403, got {}".format(c_deny))
            c3, b3 = await _req_pipe(ws, "POST", "/api/file?path=" + rel, txt, hdrs=tok_h)
            _assert(c3 == 200 and json.loads(b3.decode("utf-8")).get("bytes") == len(txt), "POST fail: {}".format(c3))
            c4, b4 = await _req_pipe(ws, "GET", "/api/file?path=" + rel, hdrs=tok_h)
            _assert(c4 == 200 and b4.decode("utf-8") == txt, "GET file fail")
            c5, b5 = await _req_pipe(ws, "DELETE", "/api/file?path=" + rel, hdrs=tok_h)
            _assert(c5 == 200 and json.loads(b5.decode("utf-8")).get("ok"), "DEL fail")
            c6, _ = await _req_pipe(ws, "GET", "/api/file?path=../../boot.py", hdrs=tok_h)
            _assert(c6 == 403, "traversal guard fail: {}".format(c6))
            # /api/run 409 guard & /api/run/status
            c7, _ = await _req_pipe(ws, "POST", "/api/run?path=apps/hello_world.py", hdrs=tok_h)
            _assert(c7 == 200, "run queue fail: {}".format(c7))
            c8, _ = await _req_pipe(ws, "POST", "/api/run?path=apps/hello_world.py", hdrs=tok_h)
            _assert(c8 == 409, "duplicate run should 409, got {}".format(c8))
            c9, b9 = await _req_pipe(ws, "GET", "/api/run/status", hdrs=tok_h)
            _assert(c9 == 200 and json.loads(b9.decode("utf-8")).get("state") == "queued", "run status fail")
            ws.pending_run = None
            ws.set_run_state("idle")
            # 401 lockout after 5 consecutive failures (Refs #23)
            bad_h = {"X-PinhOS-Token": "0000000000000000"}
            c_lock = 0
            for _ in range(5):
                c_lock, _ = await _req_pipe(ws, "GET", "/api/status", hdrs=bad_h)
            _assert(c_lock == 429, "5th bad token should 429 lockout, got {}".format(c_lock))
        finally:
            await ws.stop_async()

    lp = asyncio.get_event_loop()
    try:
        lp.run_until_complete(_run())
        gc.collect(); gc.collect()
        m0 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        lp.run_until_complete(_run())
        gc.collect(); gc.collect()
        m1 = gc.mem_free() if hasattr(gc, "mem_free") else 262144
        delta = max(0, m0 - m1)
        _assert(delta < 8192, "SRAM delta {}B >= 8192B".format(delta))
        # Regression check (#29): _init_interactive_services() honors webportal_autostart=True
        # even when start(..., interactive=False) was used (as in picocalc.ps1 upload_and_start).
        import main as _pm
        _rs = _pm.runtime_state
        _prev_done = _rs.get("_interactive_init_done", False)
        _prev_wbg = _rs.get("wifi_bg_pending", False)
        _prev_stab = _rs.get("stabilized", False)
        _prev_sl = _rs.get("serial_link", False)
        _rs["_interactive_init_done"] = False
        _rs["wifi_bg_pending"] = False
        _rs["stabilized"] = False  # Keep WDT unarmed during selftest
        _rs["serial_link"] = True
        try:
            class _FakeCfg:
                def get(self, k, d=None):
                    return {"webportal_autostart": True, "webportal_port": 8080}.get(k, d)
            ran = _pm._init_interactive_services(board, _FakeCfg(), None)
            _assert(ran and _rs.get("wifi_bg_pending") and _rs.get("web_active"), "autostart regression (#29)")
            _assert(not _pm._init_interactive_services(board, _FakeCfg(), None), "autostart not idempotent (#29)")
        finally:
            _pm.stop_webportal()
            _rs["_interactive_init_done"] = _prev_done
            _rs["wifi_bg_pending"] = _prev_wbg
            _rs["stabilized"] = _prev_stab
            _rs["serial_link"] = _prev_sl
            gc.collect()
    finally:
        try: os.remove(full)
        except OSError: pass
        board.ensure_serial_repl()

    # Verify #58 (Legal viewer), #62 (12h/24h + EU/US/ISO date), #75 (per-app logs), #77 (policy gate)
    import sys
    gc.collect()
    from core.config import format_time, format_date
    _dt = (2026, 11, 27, 4, 15, 7, 9, 0)
    _assert(format_time(_dt, {"time_format": "24h"}) == "15:07" and format_time(_dt, {"time_format": "12h"}) == "3:07P", "time_fmt fail")
    _assert(format_time((2026, 1, 1, 0, 0, 5, 0, 0), {"time_format": "12h"}) == "12:05A", "12h midnight fail")
    _assert(format_date(_dt, {"date_format": "DMY"}) == "27/11/2026" and format_date(_dt, {"date_format": "MDY"}) == "11/27/2026", "date_fmt fail")
    import ui._legal_view as _lv_t
    _ll = _lv_t.build_legal_lines(root=root, cols=49)
    _assert(len(_ll) >= 12 and any("PolyForm" in x[0] for x in _ll), "legal_view fail")
    _ll = _lv_t = None
    sys.modules.pop("ui._legal_view", None)
    gc.collect()
    from core.sandbox import parse_app_meta, inspect_app, SandboxPolicyError
    _m = inspect_app(root.rstrip("/") + "/apps/wifi_spectrum.py", strict=True)
    _assert(_m.get("needs_radio") is True and _m.get("min_block", 0) >= 16384, "wifi_spectrum policy fail")
    _blk = False
    try:
        parse_app_meta('APP_META={"id":"ok_id","name":"x","version":"1","category":"u","entry":"main","min_sram":16384,"ui_modes":["gui"]}\ndef main(ctx): machine.Pin(1)\n', strict=True)
    except SandboxPolicyError:
        _blk = True
    _assert(_blk, "SandboxPolicyError did not block machine.Pin")
    sys.modules.pop("core.sandbox", None)
    gc.collect()

    return "HTTP 200 ({},/,st,401/403,R/W/D,autostart) d={}B".format(mode[0], delta)

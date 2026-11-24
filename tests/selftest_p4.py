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


async def _req_pipe(ws, m, tgt, body=None, collect_body=True):
    bb = body.encode("utf-8") if isinstance(body, str) else (body or b"")
    raw = "{} {} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(m, tgt, len(bb)).encode("utf-8") + bb
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
    rel = ".swap/_gate12_web.txt"
    full = root.rstrip("/") + "/" + rel
    txt = "PinhOS Phase 4 WebPortal Loopback OK!"
    mode = ["tcp"]

    async def _run():
        ws = WebServer(board=board, manifest=manifest, root=root, host="0.0.0.0", port=8080)
        await ws.start_async()
        try:
            tcp = True
            try:
                c1, b1 = await _req_tcp("127.0.0.1", 8080, "GET", "/")
                mode[0] = "tcp"
            except OSError:
                tcp = False
                mode[0] = "pipe"
                c1, b1 = await _req_pipe(ws, "GET", "/", collect_body=False)
            req = (lambda m, t, b=None: _req_tcp("127.0.0.1", 8080, m, t, b)) if tcp else (lambda m, t, b=None: _req_pipe(ws, m, t, b))
            _assert(c1 == 200 and b"PinhOS" in b1, "GET / fail: {}".format(c1))
            c2, b2 = await req("GET", "/api/status")
            st = json.loads(b2.decode("utf-8"))
            _assert(c2 == 200 and st.get("ok") and "sram_free" in st and st.get("root") == root.rstrip("/"), "status fail")
            c3, b3 = await req("POST", "/api/file?path=" + rel, txt)
            _assert(c3 == 200 and json.loads(b3.decode("utf-8")).get("bytes") == len(txt), "POST fail")
            c4, b4 = await req("GET", "/api/file?path=" + rel)
            _assert(c4 == 200 and b4.decode("utf-8") == txt, "GET file fail")
            c5, b5 = await req("DELETE", "/api/file?path=" + rel)
            _assert(c5 == 200 and json.loads(b5.decode("utf-8")).get("ok"), "DEL fail")
            c6, _ = await req("GET", "/api/file?path=../../boot.py")
            _assert(c6 == 403, "traversal guard fail: {}".format(c6))
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
    finally:
        try: os.remove(full)
        except OSError: pass
        board.ensure_serial_repl()
    return "HTTP 200 ({},/,st,R/W/D,403) d={}B".format(mode[0], delta)

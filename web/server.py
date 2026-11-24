# PinhOS Phase 4 — Cooperative uasyncio WebPortal HTTP Server (web/server.py)
# Strict RP2350 SRAM discipline: max_conns=3, 5s timeout, <=1KB chunked SD streaming,
# PINHOS_ROOT path-traversal guard, board.* HAL routing, gc.collect() per request.

import os
import gc
import json

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from core.config import PINHOS_ROOT, _mkdir_p

CHUNK = 1024
MAX_SYNTAX = 32768
MAX_JSON = 1024

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".py": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".bmp": "image/bmp",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

_STAT = {
    200: "OK", 204: "No Content", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 409: "Conflict", 413: "Too Large", 429: "Too Many Requests",
    500: "Server Error", 503: "Service Unavailable",
}

WEB_LOG_MAX = 16384
_WRITE_PREFIXES = ("apps/", "tools/", "themes/")
_WRITE_EXACT = ("apps", "tools", "themes", "notes.txt", "config.json")
_READ_DENY_EXACT = ("wifi.json", "boot_state.json", "rtc_state.json", "logs/breadcrumb.json", ".swap")
_READ_DENY_PREFIXES = (".swap/",)
_AUTH_MAX_FAILS = 5
_AUTH_LOCK_MS = 30000


def _gen_token():
    """Generate an 8-byte (16-hex-char) random token; fail closed if os.urandom is unavailable (Refs #23)."""
    raw = os.urandom(8)
    if not raw or len(raw) < 8:
        raise RuntimeError("os.urandom failed to generate 8-byte WebPortal token")
    return "".join("{:02x}".format(b) for b in raw)


def _is_read_denied(rel):
    """Denylist sensitive credential/state files from WebPortal read/listing even when authenticated (Refs #23)."""
    if not rel:
        return False
    r = str(rel).strip("/")
    if r in _READ_DENY_EXACT:
        return True
    for pre in _READ_DENY_PREFIXES:
        if r.startswith(pre):
            return True
    return False


def _const_eq(a, b):
    if not isinstance(a, str) or not isinstance(b, str) or len(a) != len(b):
        return False
    diff = 0
    for i in range(len(a)):
        diff |= ord(a[i]) ^ ord(b[i])
    return diff == 0


def _is_write_allowed(rel):
    if not rel:
        return False
    r = str(rel).strip("/")
    if r in _WRITE_EXACT:
        return True
    for pre in _WRITE_PREFIXES:
        if r.startswith(pre):
            return True
    return False


def _origin_host(origin):
    s = str(origin or "").strip().lower()
    if s.startswith("http://"):
        s = s[7:]
    elif s.startswith("https://"):
        s = s[8:]
    else:
        return ""
    return s.split("/", 1)[0]


def _urldec(s):
    if not s or ("%" not in s and "+" not in s):
        return s
    s = s.replace("+", " ")
    out = bytearray()
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "%" and i + 2 < n:
            try:
                out.append(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.extend(c.encode("utf-8"))
        i += 1
    try:
        return out.decode("utf-8")
    except Exception:
        return out.decode("latin-1")


def _parse_qs(qs):
    p = {}
    if not qs:
        return p
    for kv in qs.split("&"):
        if not kv:
            continue
        if "=" in kv:
            k, v = kv.split("=", 1)
            p[_urldec(k)] = _urldec(v)
        else:
            p[_urldec(kv)] = ""
    return p


def _mime(path):
    low = str(path).lower()
    d = low.rfind(".")
    return _MIME.get(low[d:], "application/octet-stream") if d >= 0 else "application/octet-stream"


def _stat(path):
    try:
        st = os.stat(path)
        return True, bool(st[0] & 0x4000), int(st[6])
    except OSError:
        return False, False, 0


async def _tick(ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(ms)
    else:
        await asyncio.sleep(ms / 1000.0)


class WebServer:
    def __init__(self, board=None, config=None, manifest=None, logger=None,
                 root=PINHOS_ROOT, host="0.0.0.0", port=8080, max_conns=3, req_timeout=5, token=None):
        self.board = board
        self.config = config
        self.manifest = manifest or {}
        self.logger = logger
        self.root = str(root or PINHOS_ROOT).rstrip("/")
        self.host = str(host or "0.0.0.0")
        self.port = int(port or 8080)
        self.max_conns = max(1, int(max_conns))
        self.req_timeout = max(1, int(req_timeout))
        self.token = str(token) if token else _gen_token()
        self._auth_fails = 0
        self._auth_lock_until = 0
        self._srv = None
        self._loop = None
        self._running = False
        self._paused = False
        self._active = 0
        self.pending_run = None
        self._run_state = {"state": "idle", "ok": True, "error": None, "sram_before": 0, "sram_after": 0, "largest_free": 0}
        self._run_queued_ms = 0
        self.pending_reboot = False
        self.log_path = self.root + "/logs/web.log"
        self._wlan = None
        try:
            import network as _nw
            self._wlan = _nw.WLAN(_nw.STA_IF)
        except Exception:
            pass

    def _pump_wifi(self):
        """Pump CYW43439 gSPI RX FIFO so incoming TCP/HTTP/ICMP packets drain within ~10-20ms."""
        w = self._wlan
        if w is not None:
            try:
                w.status("rssi")
            except Exception:
                pass

    def _wlog(self, msg):
        """Append a compact timestamped line with date + boot_id to /sd/pinhos/logs/web.log (#22)."""
        try:
            ex, _, sz = _stat(self.log_path)
            if ex and sz >= WEB_LOG_MAX:
                bak = self.log_path + ".1"
                try:
                    os.remove(bak)
                except OSError:
                    pass
                try:
                    os.rename(self.log_path, bak)
                except OSError:
                    pass
            try:
                from core.logger import format_log_prefix
                pfx = format_log_prefix()
            except Exception:
                ts = self.board.get_timestamp_str(False) if (self.board and hasattr(self.board, "get_timestamp_str")) else "~UNSYNCED"
                pfx = "[{}]".format(ts)
            with open(self.log_path, "a") as f:
                f.write("{} {}\n".format(pfx, str(msg)[:160]))
        except Exception:
            pass

    @property
    def running(self):
        return self._running and (self._srv is not None)

    def _loop_obj(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def start_async(self):
        if self._running and self._srv is not None:
            return True
        # Close any orphaned Server socket left by a prior REPL Ctrl+C / reload to avoid lwIP ENOMEM
        try:
            import builtins as _bi
            old = getattr(_bi, "_pinhos_web_srv", None)
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
                try:
                    if hasattr(old, "wait_closed"):
                        await old.wait_closed()
                except Exception:
                    pass
                setattr(_bi, "_pinhos_web_srv", None)
        except Exception:
            pass
        gc.collect()
        self._srv = await asyncio.start_server(self._handle_client, self.host, self.port, backlog=self.max_conns)
        try:
            import builtins as _bi
            setattr(_bi, "_pinhos_web_srv", self._srv)
        except Exception:
            pass
        self._running = True
        self._active = 0
        self.pending_run = None
        self.pending_reboot = False
        self._wlog("START {}:{} max_conns={} free={}B".format(
            self.host, self.port, self.max_conns, gc.mem_free() if hasattr(gc, "mem_free") else 0
        ))
        if self.logger:
            try:
                self.logger.info("WEB: Started {}:{}".format(self.host, self.port))
            except Exception:
                pass
        return True

    def start(self):
        return bool(self._loop_obj().run_until_complete(self.start_async()))

    async def stop_async(self):
        self._running = False
        s = self._srv
        self._srv = None
        try:
            import builtins as _bi
            if getattr(_bi, "_pinhos_web_srv", None) is s:
                setattr(_bi, "_pinhos_web_srv", None)
        except Exception:
            pass
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
            if hasattr(s, "wait_closed"):
                try:
                    await s.wait_closed()
                except Exception:
                    pass
        try:
            await asyncio.sleep_ms(10)
        except Exception:
            pass
        self._active = 0
        self._wlog("STOP")
        gc.collect()
        return True

    def stop(self):
        if not self._running and self._srv is None:
            return True
        self._paused = False
        return bool(self._loop_obj().run_until_complete(self.stop_async()))

    def pause(self):
        """Close listening socket while keeping WLAN up for radio-heavy tools (#17)."""
        if not self._running or self._paused:
            return False
        self._paused = True
        self.stop()
        self._paused = True
        return True

    def resume(self):
        """Rebind listening socket after radio-heavy tool completes (#17)."""
        if not self._paused:
            return False
        self._paused = False
        try:
            return self.start()
        except Exception:
            return False

    def set_run_state(self, state, res=None):
        st = self._run_state
        st["state"] = str(state)
        if isinstance(res, dict):
            st["ok"] = bool(res.get("ok"))
            st["error"] = res.get("error")
            st["sram_before"] = int(res.get("sram_before", 0))
            st["sram_after"] = int(res.get("sram_after", 0))
            try:
                from core.memutil import largest_free
                st["largest_free"] = int(largest_free())
            except Exception:
                st["largest_free"] = 0

    def step(self, ms=15):
        if not self._running:
            return
        self._pump_wifi()
        lp = self._loop_obj()
        lp.run_until_complete(_tick(max(1, int(ms))))
        # While HTTP requests are actively streaming, grant extra cooperative slices (up to ~140ms)
        # so multi-chunk responses finish in ~100ms instead of 2-3s while keeping UI responsive.
        n = 0
        while self._running and self._active > 0 and n < 12:
            self._pump_wifi()
            lp.run_until_complete(_tick(10))
            n += 1

    def resolve_path(self, rel, base=None):
        root = (base or self.root).rstrip("/")
        raw = str(rel or "").replace("\\", "/").strip()
        if "\x00" in raw:
            return None, None
        if raw == root:
            raw = ""
        elif raw.startswith(root + "/"):
            raw = raw[len(root) + 1:]
        parts = []
        for seg in raw.lstrip("/").split("/"):
            if not seg or seg == ".":
                continue
            if seg == "..":
                return None, None
            parts.append(seg)
        clean = "/".join(parts)
        full = root if not clean else (root + "/" + clean)
        if full != root and not full.startswith(root + "/"):
            return None, None
        return full, clean

    async def _hdr(self, w, code, ct, clen=None, extra=None):
        h = ["HTTP/1.1 {} {}".format(code, _STAT.get(code, "OK")), "Content-Type: " + ct, "Connection: close"]
        if clen is not None:
            h.append("Content-Length: {}".format(int(clen)))
        if extra:
            for k, v in extra:
                h.append(k + ": " + v)
        h.append("")
        h.append("")
        w.write("\r\n".join(h).encode("utf-8"))
        await w.drain()

    async def _json(self, w, code, obj):
        b = json.dumps(obj).encode("utf-8")
        h = (
            "HTTP/1.1 {} {}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-store\r\n"
            "Content-Length: {}\r\n\r\n"
        ).format(code, _STAT.get(code, "OK"), len(b)).encode("utf-8")
        # Single write avoids TCP Nagle + Windows Delayed-ACK 200ms stall
        w.write(h + b)
        await w.drain()

    async def _err(self, w, code, msg):
        await self._json(w, code, {"ok": False, "error": str(msg)})

    async def _stream_file(self, w, path, cc=None, dl=None):
        ex, isd, sz = _stat(path)
        if not ex or isd:
            await self._err(w, 404, "Not found")
            return
        ext = []
        if cc:
            ext.append(("Cache-Control", cc))
        if dl:
            ext.append(("Content-Disposition", 'attachment; filename="{}"'.format(dl)))
        await self._hdr(w, 200, _mime(path), sz, ext)
        buf = bytearray(CHUNK)
        mv = memoryview(buf)
        f = open(path, "rb")
        try:
            while True:
                n = f.readinto(buf)
                if not n:
                    break
                w.write(mv[:n])
                await w.drain()
        finally:
            f.close()
            mv = buf = None

    async def _read_json(self, r, clen, extra=b""):
        if clen <= 0:
            return {}
        if clen > MAX_JSON:
            return None
        ch = [extra] if extra else []
        rem = max(0, clen - len(extra))
        while rem > 0:
            c = await asyncio.wait_for(r.read(min(512, rem)), self.req_timeout)
            if not c:
                break
            ch.append(c)
            rem -= len(c)
        try:
            return json.loads(b"".join(ch).decode("utf-8"))
        except Exception:
            return {}

    async def _drain(self, r, clen, extra=b""):
        rem = max(0, int(clen) - len(extra))
        while rem > 0:
            c = await asyncio.wait_for(r.read(min(CHUNK, rem)), self.req_timeout)
            if not c:
                break
            rem -= len(c)

    async def _read_req_head(self, r):
        """Read HTTP/1.1 request line (bounded timeout) + security/length headers."""
        line = await asyncio.wait_for(r.readline(), 3)
        if not line:
            return None, None, 0, b"", {}
        pts = line.decode("utf-8", "ignore").strip().split()
        if len(pts) < 2:
            return "", "", 0, b"", {}
        meth, tgt = pts[0].upper(), pts[1]
        clen = 0
        hdrs = {}
        for _ in range(32):
            hl = await asyncio.wait_for(r.readline(), 2)
            if not hl or hl in (b"\r\n", b"\n"):
                break
            hs = hl.decode("utf-8", "ignore")
            if ":" in hs:
                k, v = hs.split(":", 1)
                kl = k.strip().lower()
                vs = v.strip()
                if kl == "content-length":
                    try:
                        clen = max(0, int(vs))
                    except ValueError:
                        clen = 0
                elif kl in ("host", "origin", "x-pinhos-token"):
                    hdrs[kl] = vs
        return meth, tgt, clen, b"", hdrs

    def _check_auth(self, meth, rt, hdrs):
        """Enforce same-origin check + X-PinhOS-Token on all /api/* & mutating endpoints with 401 lockout (Refs #23)."""
        orig = hdrs.get("origin", "")
        if orig:
            oh = _origin_host(orig)
            hh = str(hdrs.get("host", "")).strip().lower()
            if not oh or not hh or oh != hh:
                return 403, "Cross-origin forbidden"
        needs_tok = (meth != "GET") or rt.startswith("/api/")
        if needs_tok:
            import time as _tm
            now = _tm.ticks_ms() if hasattr(_tm, "ticks_ms") else int(_tm.time() * 1000)
            if self._auth_lock_until:
                rem = _tm.ticks_diff(self._auth_lock_until, now) if hasattr(_tm, "ticks_diff") else (self._auth_lock_until - now)
                if rem > 0:
                    return 429, "Auth locked ({}s)".format(max(1, (rem + 999) // 1000))
                self._auth_lock_until = 0
            tok = hdrs.get("x-pinhos-token", "")
            if not _const_eq(tok, self.token):
                self._auth_fails += 1
                if self._auth_fails >= _AUTH_MAX_FAILS:
                    self._auth_fails = 0
                    self._auth_lock_until = _tm.ticks_add(now, _AUTH_LOCK_MS) if hasattr(_tm, "ticks_add") else (now + _AUTH_LOCK_MS)
                    return 429, "Too many auth failures (locked 30s)"
                return 401, "Unauthorized (X-PinhOS-Token required)"
            self._auth_fails = 0
        return 0, ""

    async def _handle_client(self, r, w):
        if self._active >= self.max_conns:
            try:
                await self._err(w, 503, "Busy")
            except Exception:
                pass
            try:
                w.close()
                if hasattr(w, "wait_closed"):
                    await w.wait_closed()
            except Exception:
                pass
            return
        self._active += 1
        meth, rt = "?", "?"
        try:
            meth, tgt, clen, extra, hdrs = await self._read_req_head(r)
            if meth is None:
                return
            if not meth:
                await self._err(w, 400, "Bad request")
                return
            if "?" in tgt:
                rt, qs = tgt.split("?", 1)
                q = _parse_qs(qs)
            else:
                rt, q = tgt, {}
            rt = _urldec(rt)
            if meth == "OPTIONS":
                await self._err(w, 405, "Method not allowed")
                return
            acode, amsg = self._check_auth(meth, rt, hdrs)
            if acode:
                await self._drain(r, clen, extra)
                await self._err(w, acode, amsg)
                return
            await self._dispatch(meth, rt, q, clen, r, w, extra)
            if rt != "/api/status":
                self._wlog("OK {} {}".format(meth, rt))
        except Exception as e:
            ename = type(e).__name__
            eno = e.args[0] if (isinstance(e, OSError) and e.args) else None
            if eno in (104, 32):
                # Silently ignore client disconnect (ECONNRESET / EPIPE) (#7)
                pass
            elif ename == "TimeoutError":
                if meth != "?":
                    self._wlog("TIMEOUT {} {}".format(meth, rt))
            else:
                self._wlog("ERR {} {} -> {}".format(meth, rt, repr(e)))
                try:
                    await self._err(w, 500, "{}: {}".format(ename, str(e))[:120])
                except Exception:
                    pass
        finally:
            try:
                w.close()
                if hasattr(w, "wait_closed"):
                    await w.wait_closed()
            except Exception:
                pass
            self._active = max(0, self._active - 1)
            gc.collect()

    async def _dispatch(self, m, rt, q, clen, r, w, extra=b""):
        if m == "GET" and rt == "/favicon.ico":
            await self._hdr(w, 204, "image/x-icon", 0)
            return
        if m == "GET" and rt in ("/", "/index.html"):
            await self._stream_file(w, self.root + "/web/static/index.html", cc="public, max-age=3600")
            return
        if m == "GET" and rt == "/api/weblog":
            await self._api_weblog(w)
            return
        if m == "GET" and rt.startswith("/static/"):
            full, _ = self.resolve_path(rt[8:], base=self.root + "/web/static")
            if not full:
                await self._err(w, 403, "Forbidden")
                return
            await self._stream_file(w, full, cc="public, max-age=3600")
            return
        if m == "GET" and rt == "/api/run/status":
            await self._json(w, 200, dict(self._run_state))
            return
        if m == "GET" and rt == "/api/status":
            await self._api_status(w)
            return
        if m == "GET" and rt == "/api/files":
            await self._api_files(w, q)
            return
        if rt == "/api/file":
            if m == "GET":
                await self._api_get(w, q)
            elif m == "POST":
                await self._api_post(r, w, q, clen, extra)
            elif m == "DELETE":
                await self._api_del(w, q)
            else:
                await self._err(w, 405, "Method not allowed")
            return
        if m == "POST" and rt == "/api/mkdir":
            await self._api_mkdir(r, w, q, clen, extra)
            return
        if m == "POST" and rt == "/api/syntax":
            await self._api_syntax(r, w, q, clen, extra)
            return
        if m == "POST" and rt == "/api/run":
            await self._api_run(r, w, q, clen, extra)
            return
        if m == "POST" and rt == "/api/screenshot":
            await self._drain(r, clen, extra)
            await self._api_shot(w)
            return
        if m == "POST" and rt == "/api/key":
            await self._api_key(r, w, q, clen, extra)
            return
        if m == "POST" and rt == "/api/reboot":
            await self._drain(r, clen, extra)
            self.pending_reboot = True
            await self._json(w, 200, {"ok": True, "rebooting": True})
            return
        await self._err(w, 404, "Not found")

    async def _api_status(self, w):
        gc.collect()
        b = self.board
        wf = {"connected": False, "ip": "127.0.0.1", "rssi": 0, "ssid": ""}
        try:
            from net.wifi import get_wifi_manager
            st = get_wifi_manager().status()
            if isinstance(st, dict):
                wf = {"connected": bool(st.get("connected")), "ip": str(st.get("ip", "0.0.0.0")),
                      "rssi": int(st.get("rssi", 0)), "ssid": str(st.get("ssid", ""))}
        except Exception:
            pass
        sw = {"files": 0, "used_kb": 0, "max_kb": 512, "pct": 0}
        try:
            from core.swap import get_swap_manager
            sw = get_swap_manager().stats()
        except Exception:
            pass
        blk = 0
        try:
            from core.memutil import largest_free
            blk = largest_free()
        except Exception:
            pass
        await self._json(w, 200, {
            "ok": True,
            "sram_free": int(gc.mem_free()) if hasattr(gc, "mem_free") else 262144,
            "sram_alloc": int(gc.mem_alloc()) if hasattr(gc, "mem_alloc") else 65536,
            "sram_largest": int(blk),
            "sram_total": int(self.manifest.get("sram_kb", 520)) * 1024,
            "swap": sw,
            "cpu_mhz": b.get_cpu_freq_mhz() if (b and hasattr(b, "get_cpu_freq_mhz")) else 150,
            "temp_c": b.get_cpu_temp_c() if (b and hasattr(b, "get_cpu_temp_c")) else 28.0,
            "battery": b.get_battery() if (b and hasattr(b, "get_battery")) else {"percent": 100, "voltage_mv": 4200, "charging": False},
            "wifi": wf,
            "version": str(self.manifest.get("version", "1.0.0-alpha.4.1")),
            "firmware_version": str(self.manifest.get("firmware_version", "")),
            "board": str(b.id) if b else "unknown",
            "root": self.root,
            "port": self.port,
        })

    async def _api_files(self, w, q):
        full, rel = self.resolve_path(q.get("path", ""))
        if not full or _is_read_denied(rel):
            await self._err(w, 403, "Forbidden")
            return
        ex, isd, _ = _stat(full)
        if not ex or not isd:
            await self._err(w, 404, "Dir not found")
            return
        ents = []
        for nm in os.listdir(full):
            if nm.startswith("."):
                continue
            item_rel = nm if not rel else (rel + "/" + nm)
            if _is_read_denied(item_rel):
                continue
            _, cd, cs = _stat(full + "/" + nm)
            ents.append({"name": nm, "path": item_rel, "type": "dir" if cd else "file", "size": 0 if cd else cs})
        ents.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
        await self._json(w, 200, {"ok": True, "root": self.root, "path": rel, "entries": ents})

    async def _api_get(self, w, q):
        full, rel = self.resolve_path(q.get("path", ""))
        if not full or not rel or _is_read_denied(rel):
            await self._err(w, 403, "Forbidden")
            return
        dl = (rel.rpartition("/")[2] or "file.bin") if q.get("download") in ("1", "true") else None
        await self._stream_file(w, full, cc="no-store", dl=dl)

    async def _api_post(self, r, w, q, clen, extra=b""):
        full, rel = self.resolve_path(q.get("path", ""))
        if not full or not rel or not _is_write_allowed(rel):
            await self._drain(r, clen, extra)
            await self._err(w, 403, "Write forbidden")
            return
        par = full.rpartition("/")[0]
        if par and par != self.root:
            _mkdir_p(par)
        wr, rem = 0, int(clen)
        is_cfg = (rel == "config.json")
        target = (full + ".webtmp") if is_cfg else full
        try:
            f = open(target, "wb")
            try:
                if extra and rem > 0:
                    take = extra[:rem]
                    f.write(take)
                    wr += len(take)
                    rem -= len(take)
                while rem > 0:
                    c = await asyncio.wait_for(r.read(min(CHUNK, rem)), self.req_timeout)
                    if not c:
                        break
                    f.write(c)
                    wr += len(c)
                    rem -= len(c)
                    c = None
                if hasattr(f, "flush"):
                    f.flush()
            finally:
                f.close()
            if is_cfg:
                try:
                    with open(target, "r") as cf:
                        parsed = json.load(cf)
                    if not isinstance(parsed, dict):
                        raise ValueError("config.json must be a JSON object")
                except Exception as je:
                    try:
                        os.remove(target)
                    except OSError:
                        pass
                    await self._err(w, 400, "Invalid JSON: " + str(je)[:80])
                    return
                try:
                    os.remove(full)
                except OSError:
                    pass
                os.rename(target, full)
        except Exception as e:
            await self._err(w, 500, str(e))
            return
        await self._json(w, 200, {"ok": True, "path": rel, "bytes": wr})

    async def _api_del(self, w, q):
        full, rel = self.resolve_path(q.get("path", ""))
        if not full or not rel or not _is_write_allowed(rel):
            await self._err(w, 403, "Delete forbidden")
            return
        ex, isd, _ = _stat(full)
        if not ex:
            await self._err(w, 404, "Not found")
            return
        try:
            os.rmdir(full) if isd else os.remove(full)
        except OSError as e:
            await self._err(w, 409, str(e))
            return
        await self._json(w, 200, {"ok": True, "path": rel})

    async def _api_mkdir(self, r, w, q, clen, extra=b""):
        b = await self._read_json(r, clen, extra)
        full, rel = self.resolve_path(q.get("path") or (b.get("path") if isinstance(b, dict) else ""))
        if not full or not rel or not _is_write_allowed(rel):
            await self._err(w, 403, "Mkdir forbidden")
            return
        if not _mkdir_p(full):
            await self._err(w, 500, "mkdir failed")
            return
        await self._json(w, 200, {"ok": True, "path": rel})

    async def _api_syntax(self, r, w, q, clen, extra=b""):
        b = await self._read_json(r, clen, extra)
        full, rel = self.resolve_path(q.get("path") or (b.get("path") if isinstance(b, dict) else ""))
        if not full or not rel:
            await self._err(w, 403, "Forbidden")
            return
        ex, isd, sz = _stat(full)
        if not ex or isd:
            await self._err(w, 404, "Not found")
            return
        if sz > MAX_SYNTAX:
            await self._err(w, 413, "File > 32 KB")
            return
        gc.collect()
        try:
            with open(full, "r") as f:
                src = f.read()
            compile(src, rel, "exec")
            src = None
            gc.collect()
            await self._json(w, 200, {"ok": True, "path": rel, "message": "Syntax OK"})
        except SyntaxError as se:
            gc.collect()
            await self._json(w, 200, {"ok": False, "path": rel, "error": str(se), "line": getattr(se, "lineno", None)})
        except Exception as e:
            gc.collect()
            await self._json(w, 200, {"ok": False, "path": rel, "error": repr(e)})

    async def _api_run(self, r, w, q, clen, extra=b""):
        b = await self._read_json(r, clen, extra)
        if self.pending_run is not None or self._run_state.get("state") in ("queued", "running"):
            await self._err(w, 409, "Run already queued or active")
            return
        full, rel = self.resolve_path(q.get("path") or (b.get("path") if isinstance(b, dict) else ""))
        if not full or not rel or not rel.endswith(".py"):
            await self._err(w, 400, "Need .py path")
            return
        ex, isd, _ = _stat(full)
        if not ex or isd:
            await self._err(w, 404, "Not found")
            return
        try:
            from core.sandbox import inspect_app
            meta = inspect_app(full)
        except Exception as e:
            await self._err(w, 400, "APP_META: " + str(e))
            return
        try:
            import time as _tm
            self._run_queued_ms = _tm.ticks_ms() if hasattr(_tm, "ticks_ms") else int(_tm.time() * 1000)
        except Exception:
            self._run_queued_ms = 0
        self._run_state = {"state": "queued", "ok": True, "error": None, "sram_before": 0, "sram_after": 0, "largest_free": 0}
        self.pending_run = (full, str(meta.get("name", rel))[:24], bool(meta.get("needs_radio") or meta.get("suspend_web")))
        await self._json(w, 200, {"ok": True, "status": "queued", "queued": True, "path": rel, "app_id": meta.get("id", ""), "name": meta.get("name", rel)})

    async def _api_shot(self, w):
        b = self.board
        if b is None or not (hasattr(b, "screenshot_iter") or hasattr(b, "capture_screenshot")):
            await self._err(w, 500, "No screenshot HAL")
            return
        rolling = self.root + "/screenshots/last.bmp"
        p = None
        if hasattr(b, "screenshot_iter"):
            for step in b.screenshot_iter(path=rolling, step_rows=32):
                if step is False:
                    self._pump_wifi()
                    await asyncio.sleep(0)
                else:
                    p = step
        else:
            p = b.capture_screenshot(path=rolling)
        if not p:
            await self._err(w, 500, "Capture failed")
            return
        if hasattr(b, "pop_pending_screenshot"):
            b.pop_pending_screenshot()
        fn = str(p).rstrip("/").rpartition("/")[2]
        await self._json(w, 200, {"ok": True, "filename": fn, "path": "screenshots/" + fn, "url": "/api/file?path=screenshots/" + fn})

    async def _api_key(self, r, w, q, clen, extra=b""):
        b = await self._read_json(r, clen, extra)
        key = q.get("k") or (b.get("key") if isinstance(b, dict) else "")
        if not key or self.board is None or not hasattr(self.board, "push_event"):
            await self._err(w, 400, "Invalid key or HAL")
            return
        self.board.push_event({"type": "key", "key": str(key)[:12], "modifiers": 0})
        await self._json(w, 200, {"ok": True, "key": str(key)[:12]})

    async def _api_weblog(self, w):
        lines = []
        try:
            with open(self.log_path, "r") as f:
                for ln in f:
                    lines.append(ln.rstrip())
                    if len(lines) > 40:
                        lines.pop(0)
        except OSError:
            lines = ["(web.log empty)"]
        await self._json(w, 200, {"ok": True, "path": "logs/web.log", "lines": lines})

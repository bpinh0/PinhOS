# PinhOS — GitHub Themes & Apps Sync (net/sync.py)
# Streams .json themes and .py apps from GitHub into /sd/pinhos/ in <=1KB chunks,
# validates themes (strict Theme schema) and apps (APP_META) before atomic install.
# Zero hardcoded GPIO pins; safe when offline.

import gc
import json
import os

from core.config import PINHOS_ROOT, load_version_manifest

DEFAULT_REPO = "bpinh0/PinhOS"
DEFAULT_BRANCH = "main"


def get_repo_info(config=None):
    """Single source of truth for OTA repo/branch: version.json (#21)."""
    m = load_version_manifest()
    ota = m.get("ota", {}) if isinstance(m, dict) else {}
    repo = ota.get("repo") or DEFAULT_REPO
    branch = ota.get("branch") or DEFAULT_BRANCH
    return str(repo).strip(), str(branch).strip()


def _feed_wdt():
    try:
        import sys as _sy
        _w = _sy.modules.get("__pinhos_wdt__")
        if _w is not None:
            _w.feed()
    except Exception:
        pass


def _http_get_stream(url, dst_path=None, max_bytes=32768):
    """
    HTTPS GET using urequests/requests (if present) or raw socket+ssl.
    If dst_path is given, streams response in 1 KB chunks to dst_path and returns byte count.
    Otherwise returns decoded text (capped at max_bytes). Socket timeout capped <= 4s for WDT (Refs #28).
    """
    gc.collect()
    _feed_wdt()
    try:
        import urequests as req_mod
    except Exception:
        try:
            import requests as req_mod
        except Exception:
            req_mod = None

    headers = {"User-Agent": "PinhOS-PicoCalc/1.0"}
    if req_mod is not None:
        try:
            r = req_mod.get(url, headers=headers, timeout=4)
        except TypeError:
            r = req_mod.get(url, headers=headers)
        try:
            _feed_wdt()
            code = getattr(r, "status_code", 200)
            if code != 200:
                raise RuntimeError("HTTP {}".format(code))
            if dst_path is not None:
                raw = getattr(r, "raw", None)
                total = 0
                with open(dst_path, "wb") as f:
                    if raw is not None and hasattr(raw, "read"):
                        while total < max_bytes:
                            _feed_wdt()
                            ch = raw.read(1024)
                            if not ch:
                                break
                            f.write(ch)
                            total += len(ch)
                    else:
                        data = r.content
                        for i in range(0, len(data), 1024):
                            _feed_wdt()
                            f.write(data[i:i + 1024])
                        total = len(data)
                return total
            return r.text
        finally:
            try:
                r.close()
            except Exception:
                pass
            gc.collect()

    # Fallback raw TLS socket GET (zero external dependency, <=4s socket timeout for WDT)
    import socket
    import ssl
    if not url.startswith("https://"):
        raise RuntimeError("Only https:// supported")
    rest = url[8:]
    host, _, path = rest.partition("/")
    path = "/" + path
    s = socket.socket()
    s.settimeout(4)
    _feed_wdt()
    addr = socket.getaddrinfo(host, 443)[0][-1]
    _feed_wdt()
    s.connect(addr)
    _feed_wdt()
    ss = ssl.wrap_socket(s, server_hostname=host)
    _feed_wdt()
    try:
        req = "GET {} HTTP/1.0\r\nHost: {}\r\nUser-Agent: PinhOS/1.0\r\nConnection: close\r\n\r\n".format(path, host)
        ss.write(req.encode())
        # Read headers
        hdr = b""
        while b"\r\n\r\n" not in hdr and len(hdr) < 4096:
            _feed_wdt()
            ch = ss.read(256)
            if not ch:
                break
            hdr += ch
        hpart, _, body = hdr.partition(b"\r\n\r\n")
        first = hpart.split(b"\r\n", 1)[0]
        if b" 200 " not in first:
            raise RuntimeError(first.decode("utf-8", "ignore")[:28])
        if dst_path is not None:
            total = 0
            with open(dst_path, "wb") as f:
                if body:
                    f.write(body); total += len(body)
                while total < max_bytes:
                    _feed_wdt()
                    ch = ss.read(1024)
                    if not ch:
                        break
                    f.write(ch); total += len(ch)
            return total
        out = bytearray(body)
        while len(out) < max_bytes:
            _feed_wdt()
            ch = ss.read(1024)
            if not ch:
                break
            out.extend(ch)
        return bytes(out).decode("utf-8", "ignore")
    finally:
        try:
            ss.close()
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass
        gc.collect()


def _check_wifi():
    from net.wifi import get_wifi_manager
    st = get_wifi_manager().status()
    if not st.get("connected"):
        raise RuntimeError("Wi-Fi not connected")


def _list_github_dir(repo, branch, subdir):
    url = "https://api.github.com/repos/{}/contents/{}?ref={}".format(repo, subdir, branch)
    txt = _http_get_stream(url, dst_path=None, max_bytes=24576)
    items = json.loads(txt)
    if not isinstance(items, list):
        raise RuntimeError("Bad GitHub listing")
    return items


def sync_themes(config=None, theme_mgr=None, progress_cb=None):
    """Sync *.json themes from GitHub repo/themes/ with strict schema validation."""
    _check_wifi()
    repo, branch = get_repo_info(config)
    items = _list_github_dir(repo, branch, "themes")
    tdir = PINHOS_ROOT + "/themes"
    synced, skipped = 0, 0
    from core.theme import load_theme_file

    for it in items:
        nm = str(it.get("name", ""))
        dl = it.get("download_url")
        if not nm.endswith(".json") or not dl or nm.startswith("."):
            continue
        if progress_cb:
            progress_cb("Theme: " + nm[:24])
        dst = tdir + "/" + nm
        tmp = dst + ".tmp"
        try:
            _http_get_stream(dl, dst_path=tmp, max_bytes=4096)
            load_theme_file(tmp, strict=True)
            try:
                os.remove(dst)
            except OSError:
                pass
            os.rename(tmp, dst)
            synced += 1
        except Exception:
            skipped += 1
            try:
                os.remove(tmp)
            except OSError:
                pass
        gc.collect()

    if theme_mgr is not None:
        theme_mgr.refresh_catalog()
    return synced, skipped


def sync_apps(config=None, progress_cb=None):
    """Sync *.py sandboxed apps from GitHub repo/apps/ with APP_META validation."""
    _check_wifi()
    repo, branch = get_repo_info(config)
    items = _list_github_dir(repo, branch, "apps")
    adir = PINHOS_ROOT + "/apps"
    synced, skipped = 0, 0
    from core.sandbox import inspect_app

    for it in items:
        nm = str(it.get("name", ""))
        dl = it.get("download_url")
        if not nm.endswith(".py") or not dl or nm.startswith("_"):
            continue
        if progress_cb:
            progress_cb("App: " + nm[:26])
        dst = adir + "/" + nm
        tmp = dst + ".tmp"
        try:
            _http_get_stream(dl, dst_path=tmp, max_bytes=32768)
            inspect_app(tmp)
            try:
                os.remove(dst)
            except OSError:
                pass
            os.rename(tmp, dst)
            synced += 1
        except Exception:
            skipped += 1
            try:
                os.remove(tmp)
            except OSError:
                pass
        gc.collect()

    return synced, skipped


def check_remote_version(config=None):
    """Fetch remote version.json from GitHub and return (local_ver, remote_ver, repo)."""
    _check_wifi()
    repo, branch = get_repo_info(config)
    url = "https://raw.githubusercontent.com/{}/{}/version.json".format(repo, branch)
    txt = _http_get_stream(url, dst_path=None, max_bytes=4096)
    data = json.loads(txt)
    local_ver = str(load_version_manifest().get("version", "?"))
    remote_ver = str(data.get("version", "?")) if isinstance(data, dict) else "?"
    return local_ver, remote_ver, repo + "@" + branch

# PinhOS — Wi-Fi Manager & Credential Store (net/wifi.py)
# Manages Pico 2W CYW43439 STA_IF scanning, non-blocking connect, multi-network
# credentials (/sd/pinhos/wifi.json), and clean disconnect. Zero hardcoded GPIO pins.

import gc
import json
import time

from core.config import PINHOS_ROOT, atomic_write_json

WIFI_CFG_PATH = PINHOS_ROOT + "/wifi.json"


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else (a - b)


class WifiManager:
    """CYW43439 Wi-Fi STA manager with persistent /sd/pinhos/wifi.json store."""

    def __init__(self, cfg_path=WIFI_CFG_PATH):
        self.cfg_path = cfg_path
        self._wlan = None
        self._ssid = ""
        self._st_cache = None
        self._st_ms = 0
        self._bg = None

    @property
    def bg_active(self):
        return self._bg is not None

    def _apply_region_and_host(self, country="XX", hostname="pinhos"):
        try:
            import network
            cc = str(country or "XX").strip().upper()
            if len(cc) == 2 and hasattr(network, "country"):
                network.country(cc)
            if hostname and hasattr(network, "hostname"):
                network.hostname(str(hostname))
        except Exception:
            pass

    def start_bg_connect(self, country="XX", timeout_s=24):
        """Start a non-blocking Wi-Fi STA association to the top saved network (0ms boot stall)."""
        self._bg = None
        st = self.load_store()
        if not st.get("auto_connect", True):
            return False, "Auto-connect disabled"
        nets = st.get("networks", [])
        if not nets:
            return False, "No saved networks"
        w = self._get_wlan()
        if w is None:
            return False, "No Wi-Fi hardware"
        top = nets[0]
        ssid = str(top.get("ssid", ""))
        pw = str(top.get("password", ""))
        if not ssid:
            return False, "Empty SSID"
        ok_ip, ip = self._has_valid_ip(w)
        if ok_ip:
            self._ssid = ssid
            return True, "Connected: {} (0ms)".format(ip)
        self._apply_region_and_host(country=country)
        try:
            if not w.active():
                w.active(True)
            try:
                w.config(pm=getattr(w, "PM_NONE", 16))
            except Exception:
                pass
            w.connect(ssid, pw)
            self._bg = {
                "ssid": ssid,
                "pw": pw,
                "t0": _ticks_ms(),
                "limit_ms": max(15000, int(timeout_s) * 1000),
                "retried": False,
            }
            return True, "Associating " + ssid
        except Exception as e:
            return False, "BG err: " + str(e)[:24]

    def step_bg_connect(self):
        """Poll non-blocking Wi-Fi association from ui_loop(). Never bounces while st==1 (JOINING)."""
        bg = self._bg
        if bg is None:
            return None, ""
        w = self._get_wlan()
        if w is None:
            self._bg = None
            return "error", "No Wi-Fi hardware"
        now = _ticks_ms()
        el = _ticks_diff(now, bg["t0"])
        ok_ip, ip = self._has_valid_ip(w)
        if ok_ip:
            self._ssid = bg["ssid"]
            self._st_cache = None
            self._bg = None
            return "connected", "Connected: {} ({}ms)".format(ip, el)
        st = 0
        try:
            st = w.status()
        except Exception:
            st = 0
        # Only retry/bounce on definite failure codes (-1/-2/-3), NEVER while JOINING (st=1) or NOIP (st=2)
        if el >= 4000 and st in (-1, -2, -3) and not bg["retried"]:
            bg["retried"] = True
            try:
                w.disconnect()
                w.connect(bg["ssid"], bg["pw"])
            except Exception:
                pass
            return "connecting", "Retry (st={}, {}ms)".format(st, el)
        if el >= bg["limit_ms"]:
            self._bg = None
            return "timeout", "Timeout (st={}, {}ms)".format(st, el)
        return "connecting", "st={}".format(st)

    def _get_wlan(self):
        if self._wlan is None:
            try:
                import network
                self._wlan = network.WLAN(network.STA_IF)
            except Exception:
                self._wlan = None
        return self._wlan

    # --- Credential Store ---

    def load_store(self):
        try:
            with open(self.cfg_path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("networks"), list):
                return data
        except Exception:
            pass
        return {"networks": [], "auto_connect": True}

    def save_store(self, data):
        return atomic_write_json(self.cfg_path, data)

    def list_saved(self):
        return list(self.load_store().get("networks", []))

    def save_network(self, ssid, password):
        st = self.load_store()
        nets = [n for n in st.get("networks", []) if n.get("ssid") != ssid]
        nets.insert(0, {"ssid": str(ssid), "password": str(password)})
        st["networks"] = nets[:8]
        return self.save_store(st)

    def forget_network(self, ssid):
        st = self.load_store()
        st["networks"] = [n for n in st.get("networks", []) if n.get("ssid") != ssid]
        return self.save_store(st)

    def get_saved_password(self, ssid):
        for n in self.list_saved():
            if n.get("ssid") == ssid:
                return str(n.get("password", ""))
        return ""

    # --- Radio Operations ---

    def poll_rx(self):
        """Pump CYW43439 gSPI RX FIFO so incoming ICMP/TCP packets don't stall on Pico 2W."""
        w = self._get_wlan()
        if w is not None:
            try:
                if w.active() and w.isconnected():
                    w.status("rssi")
            except Exception:
                pass

    def status(self, force=False):
        now = _ticks_ms()
        if (not force) and self._st_cache is not None and _ticks_diff(now, self._st_ms) < 5000:
            return dict(self._st_cache)
        w = self._get_wlan()
        if w is None:
            return {"avail": False, "active": False, "connected": False, "ssid": "", "ip": "N/A", "gw": "N/A", "rssi": 0}
        try:
            active = bool(w.active())
            conn = bool(w.isconnected()) if active else False
            ip = gw = "0.0.0.0"
            rssi = 0
            ssid = self._ssid
            if conn:
                cfg = w.ifconfig()
                ip, gw = cfg[0], cfg[2]
                try:
                    rssi = int(w.status("rssi"))
                except Exception:
                    rssi = 0
                if not ssid:
                    try:
                        s = w.config("essid")
                        if s:
                            ssid = s.decode() if isinstance(s, (bytes, bytearray)) else str(s)
                            self._ssid = ssid
                    except Exception:
                        pass
            res = {"avail": True, "active": active, "connected": conn, "ssid": ssid, "ip": ip, "gw": gw, "rssi": rssi}
            self._st_cache = res
            self._st_ms = now
            return dict(res)
        except Exception:
            return {"avail": False, "active": False, "connected": False, "ssid": "", "ip": "ERR", "gw": "ERR", "rssi": 0}

    def _radio_up(self, w, bounce=False):
        """Bring CYW43439 STA radio up with WLAN.PM_NONE (16) so incoming TCP/ARP never sleeps."""
        self._st_cache = None
        if bounce and w.active():
            try:
                if w.isconnected():
                    w.disconnect()
                    _sleep_ms(120)
            except Exception:
                pass
            try:
                w.active(False)
                _sleep_ms(300)
            except Exception:
                pass
        if not w.active():
            w.active(True)
            _sleep_ms(500)
        try:
            w.config(pm=getattr(w, "PM_NONE", 16))
        except Exception:
            pass

    def _has_valid_ip(self, w):
        try:
            if not w.isconnected():
                return False, "0.0.0.0"
            ip = str(w.ifconfig()[0]).strip()
            if ip and ip not in ("0.0.0.0", "N/A", "ERR"):
                return True, ip
        except Exception:
            pass
        return False, "0.0.0.0"

    def scan(self):
        """Two-pass 2.4 GHz Wi-Fi scan merged by strongest RSSI for Pico 2W reliability."""
        w = self._get_wlan()
        if w is None:
            return []
        try:
            self._radio_up(w)
        except Exception:
            return []
        seen = {}
        passes = 1
        try:
            import builtins as _bi
            if getattr(_bi, "_pinhos_web_srv", None) is None:
                passes = 2
        except Exception:
            passes = 2
        for attempt in range(passes):
            try:
                raw = w.scan()
            except Exception:
                raw = []
            for item in raw:
                try:
                    ssid = item[0].decode("utf-8", "ignore") if isinstance(item[0], (bytes, bytearray)) else str(item[0])
                    ssid = ssid.strip()
                    if not ssid:
                        continue
                    rssi = int(item[3])
                    sec = int(item[4]) if len(item) > 4 else 0
                    if ssid not in seen or rssi > seen[ssid]["rssi"]:
                        seen[ssid] = {"ssid": ssid, "rssi": rssi, "sec": sec}
                except Exception:
                    pass
            if attempt == 0:
                try:
                    import sys as _sy
                    _wd = _sy.modules.get("__pinhos_wdt__")
                    if _wd is not None:
                        _wd.feed()
                except Exception:
                    pass
                _sleep_ms(250)
        res = sorted(seen.values(), key=lambda x: x["rssi"], reverse=True)
        gc.collect()
        return res

    def connect(self, ssid, password="", timeout_s=24, cancel_cb=None, save=True, status_cb=None, max_attempts=3):
        """
        Connect to Wi-Fi SSID with a 3-attempt retry loop, hard CYW43 radio bounce between
        attempts, PM_NONE power policy, strict global timeout cap, and instant ESC cancel.
        status_cb(phase_str, elapsed_s, timeout_s, st_code)
        Returns (ok_bool, message_str).
        """
        w = self._get_wlan()
        if w is None:
            return False, "No Wi-Fi hardware"

        attempts = max(1, min(5, int(max_attempts)))
        total_limit_s = max(attempts * 6, int(timeout_s))
        per_attempt_s = max(6, total_limit_s // attempts)
        total_limit_ms = total_limit_s * 1000
        att_limit_ms = per_attempt_s * 1000
        t_global = _ticks_ms()
        last_st = 0
        last_reason = "Timeout"

        def _cancelled():
            return bool(cancel_cb is not None and cancel_cb())

        def _wait_ms(ms):
            t_w = _ticks_ms()
            while _ticks_diff(_ticks_ms(), t_w) < ms:
                if _cancelled():
                    return True
                if _ticks_diff(_ticks_ms(), t_global) >= total_limit_ms:
                    return False
                _sleep_ms(50)
            return False

        def _emit(phase, st_code=0):
            if status_cb is not None:
                try:
                    el_total_s = min(total_limit_s, max(0, _ticks_diff(_ticks_ms(), t_global) // 1000))
                    status_cb(phase, el_total_s, total_limit_s, st_code)
                except Exception:
                    pass

        # Fast path: already connected to the requested SSID with a valid IP
        try:
            ok_ip, cur_ip = self._has_valid_ip(w)
            if ok_ip:
                cur_ssid = self._ssid
                try:
                    s = w.config("essid")
                    if s:
                        cur_ssid = s.decode() if isinstance(s, (bytes, bytearray)) else str(s)
                except Exception:
                    pass
                if cur_ssid == str(ssid):
                    self._ssid = str(ssid)
                    if save:
                        self.save_network(ssid, password)
                    _emit("Connected!", 3)
                    return True, "Connected: " + cur_ip
        except Exception:
            pass

        for attempt in range(1, attempts + 1):
            if _ticks_diff(_ticks_ms(), t_global) >= total_limit_ms:
                break
            tag = "[{}/{}] ".format(attempt, attempts)
            t_att = _ticks_ms()
            if _cancelled():
                return False, "Cancelled"

            try:
                # Attempt 1: soft disconnect if active; Attempts 2..N: hard radio power-cycle
                _emit(tag + ("Resetting radio..." if attempt > 1 else "Initializing radio..."), 0)
                if attempt > 1:
                    self._radio_up(w, bounce=True)
                else:
                    if w.active():
                        try:
                            if w.isconnected():
                                w.disconnect()
                            if _wait_ms(180):
                                return False, "Cancelled"
                        except Exception:
                            pass
                        try:
                            w.config(pm=getattr(w, "PM_NONE", 16))
                        except Exception:
                            pass
                    else:
                        self._radio_up(w, bounce=False)

                if _cancelled():
                    return False, "Cancelled"

                # Only warm-up scan on Attempt 2, plus 300ms settle so w.connect() never collides with scan
                if attempt == 2:
                    _emit(tag + "Refreshing channel...", 0)
                    try:
                        w.scan()
                    except Exception:
                        pass
                    if _wait_ms(300):
                        return False, "Cancelled"

                _emit(tag + "Associating...", 1)
                w.connect(ssid, password)
                # Give CYW43439 WPA2 4-way handshake a 1.2s quiet window (cancellable every 50ms)
                if _wait_ms(1200):
                    try:
                        w.disconnect()
                    except Exception:
                        pass
                    return False, "Cancelled"
            except Exception as e:
                last_reason = "Err: " + str(e)[:18]
                continue

            last_rep_s = -1
            neg_hits = 0

            while _ticks_diff(_ticks_ms(), t_att) < att_limit_ms and _ticks_diff(_ticks_ms(), t_global) < total_limit_ms:
                if _cancelled():
                    try:
                        w.disconnect()
                    except Exception:
                        pass
                    return False, "Cancelled"

                try:
                    ok_ip, ip = self._has_valid_ip(w)
                    if ok_ip:
                        self._ssid = str(ssid)
                        self._st_cache = None
                        if save:
                            self.save_network(ssid, password)
                        _emit(tag + "Connected!", 3)
                        return True, "Connected: " + ip

                    st = w.status()
                    last_st = st
                    el_att_ms = _ticks_diff(_ticks_ms(), t_att)
                    el_s = min(total_limit_s, _ticks_diff(_ticks_ms(), t_global) // 1000)

                    if el_s != last_rep_s:
                        last_rep_s = el_s
                        if st == 2 or w.isconnected():
                            ph = tag + "DHCP IP..."
                        elif st == 1:
                            ph = tag + "Authenticating..."
                        elif st == 0:
                            ph = tag + "Linking..."
                        else:
                            ph = "{}Handshake (st={})".format(tag, st)
                        _emit(ph, st)

                    # Detect terminal CYW43 failure states after 3.5s into this attempt
                    if el_att_ms >= 3500 and st in (-1, -2, -3):
                        neg_hits += 1
                        if st == -3:
                            last_reason = "Auth failed (st=-3)"
                        elif st == -2:
                            last_reason = "AP not found (st=-2)"
                        else:
                            last_reason = "Link fail (st=-1)"
                        if neg_hits >= 2:
                            break
                except Exception:
                    pass
                if _wait_ms(250):
                    try:
                        w.disconnect()
                    except Exception:
                        pass
                    return False, "Cancelled"

            # Final check at end of attempt window
            ok_ip, ip = self._has_valid_ip(w)
            if ok_ip:
                self._ssid = str(ssid)
                if save:
                    self.save_network(ssid, password)
                _emit(tag + "Connected!", 3)
                return True, "Connected: " + ip

        return False, "{} after {}/{} (st={})".format(last_reason, attempts, attempts, last_st)

    def set_auto_connect(self, enabled):
        st = self.load_store()
        st["auto_connect"] = bool(enabled)
        return self.save_store(st)

    def get_auto_connect(self):
        return bool(self.load_store().get("auto_connect", True))

    def auto_connect_saved(self, timeout_s=24, max_attempts=1, status_cb=None):
        """Try connecting to the most-recent saved network (1 attempt by default on boot) if auto_connect is enabled."""
        st = self.load_store()
        if not st.get("auto_connect", True):
            return False, "Auto-connect disabled"
        nets = st.get("networks", [])
        if not nets:
            return False, "No saved networks"
        top = nets[0]
        return self.connect(
            top.get("ssid", ""),
            top.get("password", ""),
            timeout_s=timeout_s,
            save=False,
            status_cb=status_cb,
            max_attempts=max_attempts,
        )

    def disconnect(self):
        w = self._get_wlan()
        if w is None:
            return False
        try:
            if w.isconnected():
                w.disconnect()
            w.active(False)
            self._ssid = ""
            self._st_cache = None
            return True
        except Exception:
            return False


WIFI_INDICATOR_MODES = ("bars", "bars_rssi", "rssi", "off")


def get_wifi_bar_info(mode, st=None):
    """
    Return (icon_level_or_None, rssi_text) for the top StatusBar:
      'bars'      -> (0..3, '')       (crisp vector Wi-Fi fan icon only)
      'bars_rssi' -> (0..3, '-58')    (vector Wi-Fi fan icon + RSSI)
      'rssi'      -> (None, '-58dB')  (numeric RSSI only)
      'off'       -> (None, '')       (disabled)
    """
    m = str(mode or "bars").lower()
    if m == "off":
        return None, ""
    if st is None:
        st = get_wifi_manager().status()
    if not st or not st.get("connected"):
        if m == "rssi":
            return None, "NO-WF"
        return 0, ""
    rssi = int(st.get("rssi", -90))
    lvl = 3 if rssi >= -60 else (2 if rssi >= -74 else 1)
    if m == "bars":
        return lvl, ""
    if m == "bars_rssi":
        return lvl, str(rssi)
    if m == "rssi":
        return None, "{}dB".format(rssi)
    return lvl, ""


def format_wifi_indicator(mode, st=None):
    """
    Format top-bar Wi-Fi signal text for 6x8 font based on config 'wifi_indicator':
      'bars'      -> 'W||||' / 'W|||.' / 'W||..' / 'W|...' / 'W----'
      'bars_rssi' -> '||| -58' (compact bars + dBm)
      'rssi'      -> '-58dB' / 'W:OFF'
      'off'       -> ''
    """
    m = str(mode or "bars").lower()
    if m == "off":
        return ""
    if st is None:
        st = get_wifi_manager().status()
    if not st or not st.get("connected"):
        return "W:OFF" if m == "rssi" else "W----"
    rssi = int(st.get("rssi", -90))
    if rssi >= -55:
        lvl = 4
    elif rssi >= -67:
        lvl = 3
    elif rssi >= -78:
        lvl = 2
    else:
        lvl = 1
    bars = ("|" * lvl) + ("." * (4 - lvl))
    if m == "bars":
        return "W" + bars
    if m == "rssi":
        return "{}dB".format(rssi)
    if m == "bars_rssi":
        return "{} {}".format(bars, rssi)
    return "W" + bars


_singleton_wifi = None


def get_wifi_manager():
    global _singleton_wifi
    if _singleton_wifi is None:
        _singleton_wifi = WifiManager()
    return _singleton_wifi


def _sntp_query(target, timeout_ms=1800, cancel_cb=None):
    """
    Non-blocking 48-byte UDP SNTP query with ARP-safe re-transmit at 550ms & 1150ms.
    Only accepts literal IPv4 strings by default so lwIP getaddrinfo() never blocks on DNS.
    """
    import socket
    import struct
    s = None
    try:
        if cancel_cb is not None and cancel_cb():
            return None, "cancelled"
        t = str(target).strip()
        addr = socket.getaddrinfo(t, 123)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setblocking(False)
        pkt = bytearray(48)
        pkt[0] = 0x1B
        s.sendto(pkt, addr)
        t0 = _ticks_ms()
        resends = 0
        wm = get_wifi_manager()
        while _ticks_diff(_ticks_ms(), t0) < timeout_ms:
            if cancel_cb is not None and cancel_cb():
                return None, "cancelled"
            wm.poll_rx()
            el = _ticks_diff(_ticks_ms(), t0)
            # Re-transmit UDP packet after initial ARP resolution window on fresh DHCP link
            if (resends == 0 and el >= 550) or (resends == 1 and el >= 1150):
                resends += 1
                try:
                    s.sendto(pkt, addr)
                except OSError:
                    pass
            try:
                data = s.recv(48)
                if data and len(data) >= 44:
                    sec = struct.unpack("!I", data[40:44])[0]
                    if sec >= 2208988800:
                        return sec - 2208988800, None
            except OSError:
                pass
            _sleep_ms(50)
        return None, "timeout"
    except Exception as e:
        return None, str(e)[:20]
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def _http_date_fallback(timeout_s=2, cancel_cb=None):
    """Strictly non-blocking fallback UTC clock sync via HTTP Date: header on 1.1.1.1:80."""
    import socket
    s = None
    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
              "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    try:
        if cancel_cb is not None and cancel_cb():
            return None
        addr = socket.getaddrinfo("1.1.1.1", 80)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            s.connect(addr)
        except OSError:
            pass
        t0 = _ticks_ms()
        limit_ms = max(1200, int(timeout_s * 1000))
        sent = False
        buf = b""
        wm = get_wifi_manager()
        while _ticks_diff(_ticks_ms(), t0) < limit_ms and len(buf) < 512:
            if cancel_cb is not None and cancel_cb():
                return None
            wm.poll_rx()
            if not sent:
                try:
                    s.send(b"HEAD / HTTP/1.0\r\nHost: 1.1.1.1\r\n\r\n")
                    sent = True
                except OSError:
                    pass
            else:
                try:
                    ch = s.recv(256)
                    if ch:
                        buf += ch
                        if b"\r\n\r\n" in buf:
                            break
                except OSError:
                    pass
            _sleep_ms(50)
        resp = buf.decode("utf-8", "ignore")
        for line in resp.split("\n"):
            if line.lower().startswith("date:"):
                # Date: Fri, 20 Nov 2026 09:22:17 GMT
                parts = line.split(":", 1)[1].strip().split()
                if len(parts) >= 5:
                    dy = int(parts[1])
                    mo = months.get(parts[2], 1)
                    yr = int(parts[3])
                    hh, mm, ss = [int(x) for x in parts[4].split(":")]
                    return time.mktime((yr, mo, dy, hh, mm, ss, 0, 0))
    except Exception:
        pass
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
    return None


def sync_ntp(board=None, tz_offset_h=0, host="162.159.200.1", timeout_s=6, cancel_cb=None, status_cb=None):
    """
    Non-blocking UDP SNTP client using literal IPv4 anycast servers ONLY (zero DNS hang):
      162.159.200.1 (Cloudflare) -> 216.239.35.0 (Google) -> 129.6.15.28 (NIST) -> HTTP 1.1.1.1 fallback.
    Verifies valid non-0.0.0.0 IP before sending UDP packets, ARP-safe re-transmits,
    and 1970/2000 epoch-safe RTC update. Returns (ok_bool, message_str).
    """
    wm = get_wifi_manager()
    st = wm.status()
    ip_addr = str(st.get("ip", "")) if isinstance(st, dict) else ""
    if not st or not st.get("connected") or not ip_addr or ip_addr in ("0.0.0.0", "N/A", "ERR"):
        return False, "Wi-Fi not connected (join Wi-Fi first)"
    try:
        h = str(host or "162.159.200.1").strip()
        # Strictly literal IPv4 targets: never call blocking DNS getaddrinfo('pool.ntp.org')!
        targets = ["162.159.200.1", "216.239.35.0", "129.6.15.28"]
        if h and h != "pool.ntp.org" and h[0].isdigit() and h not in targets:
            targets.insert(0, h)

        unix_sec = None
        last_err = "timeout"
        per_ms = 1800
        for idx, target in enumerate(targets):
            if cancel_cb is not None and cancel_cb():
                return False, "NTP cancelled"
            if status_cb is not None:
                try:
                    status_cb("NTP [{}/{}] {}...".format(idx + 1, len(targets), target[:14]))
                except Exception:
                    pass
            unix_sec, last_err = _sntp_query(target, timeout_ms=per_ms, cancel_cb=cancel_cb)
            if last_err == "cancelled":
                return False, "NTP cancelled"
            if unix_sec is not None:
                break

        epoch_yr = time.gmtime(0)[0]
        if unix_sec is not None:
            # Convert unix (1970) seconds to MicroPython port epoch (1970 or 2000)
            mp_sec = int(unix_sec) - (946684800 if epoch_yr == 2000 else 0)
        else:
            if cancel_cb is not None and cancel_cb():
                return False, "NTP cancelled"
            if status_cb is not None:
                try:
                    status_cb("NTP HTTP 1.1.1.1...")
                except Exception:
                    pass
            # Strictly non-blocking fallback to HTTP Date: header on 1.1.1.1:80
            mp_sec = _http_date_fallback(timeout_s=2, cancel_cb=cancel_cb)
            if mp_sec is None:
                return False, "NTP " + str(last_err)

        local_sec = int(mp_sec) + (int(tz_offset_h) * 3600)
        tm = time.gmtime(local_sec)
        # machine.RTC().datetime -> (year, month, day, weekday, hour, minute, second, sub)
        dt = (tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0)
        if board is not None and hasattr(board, "set_rtc_datetime"):
            board.set_rtc_datetime(dt)
        else:
            import machine
            machine.RTC().datetime(dt)
        ts = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}".format(dt[0], dt[1], dt[2], dt[4], dt[5])
        return True, "NTP OK: " + ts
    except Exception as e:
        return False, "NTP err: " + str(e)[:24]
    finally:
        gc.collect()

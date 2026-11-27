# PinhOS Phase 1 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Canonical Layout & Persistent Configuration Manager (core/config.py)
# Zero hardcoded GPIO pins or hardware bus dependencies.

import os
import json

PINHOS_ROOT = "/sd/pinhos"

CANONICAL_SUBDIRS = (
    "boards",
    "core",
    "ui",
    "net",
    "web",
    "web/static",
    "tools",
    "apps",
    "themes",
    "fonts",
    "banners",
    ".swap",
    "logs",
    "screenshots",
    "tests",
)

DEFAULT_VERSION_MANIFEST = {
    "name": "PinhOS",
    "version": "1.0.0-alpha.5.1.2",
    "phase": "5.1",
    "codename": "Core UI, Theme v2 & RTC",
    "build_timestamp": "2026-11-24T11:55:00Z",
    "build_id": "20261124.1",
    "arch": "armv7emsp",
    "mcu": "RP2350",
    "sram_kb": 520,
    "board_default": "picocalc",
    "ota": {
        "channel": "alpha",
        "repo": "bpinh0/PinhOS",
        "branch": "main",
        "manifest_url": "https://raw.githubusercontent.com/bpinh0/PinhOS/main/version.json",
    },
}

DEFAULT_CONFIG = {
    "board": "picocalc",
    "ui_mode": "gui",
    "boot_screen": "desktop",
    "launcher_layout": "grid",
    "theme": "cyber_amber",
    "lcd_brightness": 80,
    "kb_brightness": 60,
    "sound": True,
    "wifi_indicator": "bars",
    "battery_indicator": "both",
    "ram_warn_pct": 40,
    "ram_crit_pct": 25,
    "cpu_warn_pct": 50,
    "cpu_crit_pct": 80,
    "bat_warn_pct": 25,
    "bat_crit_pct": 10,
    "sleep_timeout_s": 300,
    "rtc_save_interval_s": 300,
    "tz_offset_h": 0,
    "time_format": "24h",
    "date_format": "YMD",
    "ntp_auto": True,
    "ntp_resync_s": 3600,
    "ntp_server": "162.159.200.1",
    "wifi_country": "XX",
    "cpu_freq_mhz": 150,
    "swap_enabled": True,
    "swap_max_kb": 512,
    "swap_low_sram": 65536,
    "boot_strike_limit": 3,
    "boot_stable_ms": 5000,
    "wdt_timeout_ms": 8000,
    "soft_wdt_s": 30,
    "webportal_autostart": False,
    "webportal_port": 8080,
}

SNAPSHOT_PATH = PINHOS_ROOT + "/config.snap.json"
LEGACY_SNAPSHOT_PATH = PINHOS_ROOT + "/config_snapshot.json"
RTC_STATE_PATH = PINHOS_ROOT + "/rtc_state.json"


def save_rtc_state(board, path=RTC_STATE_PATH):
    """Persist current RTC datetime tuple to SD so manual/synced time survives power-off."""
    if board is None or not hasattr(board, "get_rtc_datetime"):
        return False
    try:
        dt = board.get_rtc_datetime()
        if dt and len(dt) >= 7 and int(dt[0]) >= 2024:
            return atomic_write_json(path, {"dt": [int(x) for x in dt[:8]]})
    except Exception:
        pass
    return False


def restore_rtc_state(board, path=RTC_STATE_PATH):
    """Restore persisted RTC datetime from SD on boot when hardware RTC reset to < 2024."""
    if board is None or not hasattr(board, "get_rtc_datetime") or not hasattr(board, "set_rtc_datetime"):
        return False
    try:
        cur = board.get_rtc_datetime()
        if cur and int(cur[0]) >= 2024:
            return False
        with open(path, "r") as f:
            data = json.load(f)
        dt = data.get("dt") if isinstance(data, dict) else None
        if isinstance(dt, list) and len(dt) >= 7 and int(dt[0]) >= 2024:
            if len(dt) == 7:
                dt.append(0)
            return bool(board.set_rtc_datetime(tuple(int(x) for x in dt[:8])))
    except Exception:
        pass
    return False


def _extract_dt(dt_or_board):
    if isinstance(dt_or_board, (tuple, list)) and len(dt_or_board) >= 7:
        return dt_or_board
    if dt_or_board is not None and hasattr(dt_or_board, "get_rtc_datetime"):
        try:
            return dt_or_board.get_rtc_datetime()
        except Exception:
            pass
    return (2026, 1, 1, 0, 0, 0, 0, 0)


def format_time(dt_or_board, cfg=None, with_sec=False):
    """Format RTC time per config time_format ('24h' or '12h') within StatusBar width budget (#62)."""
    dt = _extract_dt(dt_or_board)
    hh, mm, ss = int(dt[4]) % 24, int(dt[5]) % 60, int(dt[6]) % 60
    tf = str(cfg.get("time_format", "24h") if cfg else "24h").lower()
    if tf == "12h":
        ap = "PM" if hh >= 12 else "AM"
        h12 = hh % 12 or 12
        if with_sec:
            return "{:02d}:{:02d}:{:02d} {}".format(h12, mm, ss, ap)
        return "{}:{:02d}{}".format(h12, mm, ap[0])
    if with_sec:
        return "{:02d}:{:02d}:{:02d}".format(hh, mm, ss)
    return "{:02d}:{:02d}".format(hh, mm)


def format_date(dt_or_board, cfg=None):
    """Format RTC date per config date_format ('DMY' EU, 'MDY' US, 'YMD' ISO) (#62)."""
    dt = _extract_dt(dt_or_board)
    yr, mo, dy = int(dt[0]), int(dt[1]), int(dt[2])
    df = str(cfg.get("date_format", "YMD") if cfg else "YMD").upper()
    if df == "DMY":
        return "{:02d}/{:02d}/{:04d}".format(dy, mo, yr)
    if df == "MDY":
        return "{:02d}/{:02d}/{:04d}".format(mo, dy, yr)
    return "{:04d}-{:02d}-{:02d}".format(yr, mo, dy)


def format_datetime(dt_or_board, cfg=None, with_sec=False):
    return format_date(dt_or_board, cfg) + " " + format_time(dt_or_board, cfg, with_sec=with_sec)


def _dir_exists(path):
    try:
        st = os.stat(path)
        # In MicroPython & POSIX, bit 0x4000 indicates directory
        return bool(st[0] & 0x4000)
    except Exception:
        return False


def _mkdir_p(path):
    """Safely create directory and parents if missing."""
    norm = path.replace("\\", "/")
    if _dir_exists(norm):
        return True
    parts = [p for p in norm.split("/") if p]
    cur = "/" if norm.startswith("/") else ""
    for part in parts:
        if not cur:
            cur = part
            if len(part) == 2 and part[1] == ":":
                continue
        elif cur == "/":
            cur = "/" + part
        else:
            cur = cur.rstrip("/") + "/" + part
        if not _dir_exists(cur):
            try:
                os.mkdir(cur)
            except Exception:
                if not _dir_exists(cur):
                    return False
    return _dir_exists(norm)


def atomic_write_json(path, data):
    """Write JSON atomically via a temporary file and rename."""
    tmp_path = path + ".tmp"
    parent = "/".join(path.rstrip("/").split("/")[:-1])
    if parent:
        _mkdir_p(parent)
    try:
        payload = json.dumps(data)
        with open(tmp_path, "w") as f:
            f.write(payload)
            if hasattr(f, "flush"):
                f.flush()
        try:
            os.remove(path)
        except Exception:
            pass
        os.rename(tmp_path, path)
        return True
    except Exception:
        # Fallback direct write if filesystem does not support rename
        try:
            with open(path, "w") as f:
                json.dump(data, f)
            return True
        except Exception:
            return False


def ensure_canonical_dirs(root=PINHOS_ROOT):
    """
    Ensure /sd/pinhos/ and all required canonical subdirectories exist on boot.
    Returns summary dict: {"root": root, "created": [...], "existing": [...], "ok": bool}
    """
    created = []
    existing = []
    ok = True

    if _dir_exists(root):
        existing.append(root)
    else:
        if _mkdir_p(root):
            created.append(root)
        else:
            ok = False

    for sub in CANONICAL_SUBDIRS:
        full = root.rstrip("/") + "/" + sub
        if _dir_exists(full):
            existing.append(full)
        else:
            if _mkdir_p(full):
                created.append(full)
            else:
                ok = False

    return {
        "root": root,
        "created": created,
        "existing": existing,
        "ok": ok,
    }


def load_version_manifest(root=PINHOS_ROOT):
    """Load version.json from root, flash '/', or current working directory."""
    candidates = [
        root.rstrip("/") + "/version.json",
        "/version.json",
        "version.json",
    ]
    for cpath in candidates:
        try:
            with open(cpath, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and "version" in data:
                target = root.rstrip("/") + "/version.json"
                if cpath != target and _dir_exists(root):
                    try:
                        os.stat(target)
                    except Exception:
                        atomic_write_json(target, data)
                return data
        except Exception:
            pass

    manifest = dict(DEFAULT_VERSION_MANIFEST)
    manifest["directories"] = [root] + [root.rstrip("/") + "/" + s for s in CANONICAL_SUBDIRS]
    if _dir_exists(root):
        atomic_write_json(root.rstrip("/") + "/version.json", manifest)
    return manifest


class ConfigManager:
    """Lightweight persistent JSON configuration manager backed by /sd/pinhos/config.json."""

    def __init__(self, config_path=None, defaults=None):
        self.path = config_path or (PINHOS_ROOT + "/config.json")
        self.defaults = dict(defaults or DEFAULT_CONFIG)
        self.data = dict(self.defaults)
        self.load()

    def load(self):
        self.data = dict(self.defaults)
        try:
            with open(self.path, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                dirty = False
                for old_k, new_k in (
                    ("cpu_mhz", "cpu_freq_mhz"),
                    ("tz_offset", "tz_offset_h"),
                    ("ntp_auto_sync", "ntp_auto"),
                    ("lcd_bright", "lcd_brightness"),
                    ("kb_bright", "kb_brightness"),
                    ("web_port", "webportal_port"),
                ):
                    if old_k in loaded:
                        if new_k not in loaded:
                            loaded[new_k] = loaded[old_k]
                        dirty = True
                for k, v in loaded.items():
                    if k in self.defaults:
                        self.data[k] = v
                    else:
                        dirty = True
                if self.data.get("ntp_server") in ("pool.ntp.org", "", None):
                    self.data["ntp_server"] = "162.159.200.1"
                    dirty = True
                if dirty:
                    self.save()
                return True
        except Exception:
            pass
        # Write clean defaults if missing or corrupted
        self.save()
        return False

    def save(self):
        return atomic_write_json(self.path, self.data)

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        if default is not None:
            return default
        return self.defaults.get(key)

    def set(self, key, value, save_now=True):
        self.data[key] = value
        if save_now:
            return self.save()
        return True

    def update(self, mapping, save_now=True):
        if isinstance(mapping, dict):
            self.data.update(mapping)
            if save_now:
                return self.save()
        return False

    def reset(self, save_now=True):
        self.data = dict(self.defaults)
        if save_now:
            return self.save()
        return True

    def has_snapshot(self, snap_path=None):
        p = snap_path or SNAPSHOT_PATH
        try:
            os.stat(p)
            return True
        except Exception:
            if snap_path is None:
                try:
                    os.stat(LEGACY_SNAPSHOT_PATH)
                    return True
                except Exception:
                    pass
            return False

    def save_snapshot(self, snap_path=None):
        """Save current configuration atomically to SD snapshot file (config.snap.json)."""
        p = snap_path or SNAPSHOT_PATH
        payload = {"snapshot_version": 1, "config": dict(self.data)}
        ok = atomic_write_json(p, payload)
        if ok and snap_path is None:
            try:
                os.remove(LEGACY_SNAPSHOT_PATH)
            except Exception:
                pass
        return ok

    def load_snapshot(self, snap_path=None, save_now=True):
        """Restore configuration from SD snapshot file (config.snap.json). Returns (ok, msg)."""
        p = snap_path or SNAPSHOT_PATH
        raw = None
        try:
            with open(p, "r") as f:
                raw = json.load(f)
        except Exception:
            if snap_path is None:
                try:
                    with open(LEGACY_SNAPSHOT_PATH, "r") as f:
                        raw = json.load(f)
                except Exception:
                    raw = None
        if raw is None:
            return False, "No snapshot on SD"
        if not isinstance(raw, dict):
            return False, "Invalid snapshot JSON"
        src = raw.get("config") if isinstance(raw.get("config"), dict) else raw
        if not isinstance(src, dict) or not src:
            return False, "Empty snapshot"
        merged = dict(self.defaults)
        merged.update(src)
        self.data = merged
        if save_now:
            self.save()
            if snap_path is None:
                self.save_snapshot()
        return True, "Snapshot restored!"

    def as_dict(self):
        return dict(self.data)

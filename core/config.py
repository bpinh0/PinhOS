# PinhOS Phase 1 — Canonical Layout & Persistent Configuration Manager (core/config.py)
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
    "tools",
    "apps",
    "themes",
    ".swap",
    "logs",
    "tests",
)

DEFAULT_VERSION_MANIFEST = {
    "name": "PinhOS",
    "version": "1.0.0-alpha.1",
    "phase": 1,
    "codename": "Foundation",
    "build_timestamp": "2026-11-18T17:30:00Z",
    "build_id": "20261118.1",
    "arch": "armv7emsp",
    "mcu": "RP2350",
    "sram_kb": 520,
    "board_default": "picocalc",
    "ota": {
        "channel": "alpha",
        "repo": "PinhOS/PinhOS",
        "branch": "main",
        "manifest_url": "https://raw.githubusercontent.com/PinhOS/PinhOS/main/version.json",
    },
}

DEFAULT_CONFIG = {
    "board": "picocalc",
    "ui_mode": "native",
    "theme": "amber_phosphor",
    "lcd_brightness": 80,
    "kb_brightness": 60,
    "sound": True,
    "swap_enabled": True,
    "swap_low_sram": 65536,
    "boot_strike_limit": 3,
    "boot_stable_ms": 5000,
    "ota_channel": "alpha",
    "ota_repo": "PinhOS/PinhOS",
    "ota_branch": "main",
}


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
                self.data.update(loaded)
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

    def as_dict(self):
        return dict(self.data)

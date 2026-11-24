# PinhOS Phase 1 — Cooperative Swap Manager (core/swap.py)
# Offloads dormant app/task state dicts to /sd/pinhos/.swap/ with corruption protection.

import os
import json
import time

from core.config import PINHOS_ROOT, _mkdir_p

SWAP_MAGIC = "PINHOS_SWAP_V1"
DEFAULT_SWAP_DIR = PINHOS_ROOT + "/.swap"


def _sanitize_app_id(app_id):
    s = str(app_id or "").strip()
    if not s:
        raise ValueError("app_id must be a non-empty string")
    safe = []
    for ch in s:
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in ("_", "-"):
            safe.append(ch)
        else:
            safe.append("_")
    return "".join(safe)[:48]


def _checksum32(text):
    """Deterministic 32-bit FNV-1a checksum over UTF-8 bytes of text."""
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


class SwapManager:
    """
    Manages serialized task & app state files in /sd/pinhos/.swap/.
    Provides atomic writes, checksum verification, corruption auto-recovery,
    and stale swap pruning.
    """

    def __init__(self, swap_dir=None, logger=None, max_kb=512):
        self.swap_dir = (swap_dir or DEFAULT_SWAP_DIR).rstrip("/")
        self.logger = logger
        self.max_kb = max(0, int(max_kb))
        _mkdir_p(self.swap_dir)

    def set_max_kb(self, max_kb):
        self.max_kb = max(0, int(max_kb))
        if self.max_kb <= 0:
            self.clear_all()
        else:
            self._enforce_quota()

    def _enforce_quota(self, reserve_bytes=0):
        if self.max_kb <= 0:
            return
        limit = self.max_kb * 1024
        entries = []
        total = 0
        try:
            for fn in os.listdir(self.swap_dir):
                if fn.endswith(".swap.json"):
                    full = "{}/{}".format(self.swap_dir, fn)
                    try:
                        st = os.stat(full)
                        sz = int(st[6])
                        mt = int(st[8]) if len(st) > 8 else 0
                        entries.append((mt, sz, full))
                        total += sz
                    except Exception:
                        pass
        except Exception:
            return
        if total + reserve_bytes <= limit:
            return
        entries.sort(key=lambda x: x[0])
        for _, sz, full in entries:
            if total + reserve_bytes <= limit:
                break
            try:
                os.remove(full)
                total = max(0, total - sz)
            except Exception:
                pass

    def _file_path(self, app_id):
        safe_id = _sanitize_app_id(app_id)
        return "{}/{}.swap.json".format(self.swap_dir, safe_id)

    def save(self, app_id, state_dict):
        """
        Persist state_dict for app_id into /sd/pinhos/.swap/<app_id>.swap.json.
        Returns True on success, False on failure.
        """
        if not isinstance(state_dict, dict):
            raise TypeError("state_dict must be a dict")
        if self.max_kb <= 0:
            return False
        _mkdir_p(self.swap_dir)
        target_path = self._file_path(app_id)
        tmp_path = target_path + ".tmp"

        try:
            payload_json = json.dumps(state_dict)
            chk = _checksum32(payload_json)
            envelope = {
                "magic": SWAP_MAGIC,
                "app_id": str(app_id),
                "ts": int(time.time()),
                "size": len(payload_json),
                "checksum": chk,
                "payload": payload_json,
            }
            raw_envelope = json.dumps(envelope)
            self._enforce_quota(reserve_bytes=len(raw_envelope))
            with open(tmp_path, "w") as f:
                f.write(raw_envelope)
                if hasattr(f, "flush"):
                    f.flush()
            try:
                os.remove(target_path)
            except Exception:
                pass
            os.rename(tmp_path, target_path)
            return True
        except Exception as e:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            if self.logger:
                self.logger.warn("Swap save failed for {}: {}".format(app_id, e))
            return False

    def load(self, app_id, default=None):
        """
        Load and verify state_dict for app_id from /sd/pinhos/.swap/.
        If missing or corrupted, cleans up the bad file and returns default (None).
        """
        target_path = self._file_path(app_id)
        try:
            os.stat(target_path)
        except Exception:
            return default

        try:
            with open(target_path, "r") as f:
                envelope = json.load(f)

            if not isinstance(envelope, dict) or envelope.get("magic") != SWAP_MAGIC:
                raise ValueError("Invalid swap magic header")

            payload_json = envelope.get("payload")
            expected_chk = envelope.get("checksum")

            if isinstance(payload_json, str):
                actual_chk = _checksum32(payload_json)
                if expected_chk != actual_chk:
                    raise ValueError("Swap checksum mismatch")
                state = json.loads(payload_json)
            elif isinstance(envelope.get("data"), dict):
                state = envelope["data"]
            else:
                raise ValueError("Missing swap payload")

            if not isinstance(state, dict):
                raise ValueError("Decoded swap payload is not a dict")

            return state
        except Exception as e:
            # Corrupted swap file: quarantine/remove so subsequent boots do not fault
            try:
                os.remove(target_path)
            except Exception:
                pass
            if self.logger:
                self.logger.warn("Corrupt swap purged for {}: {}".format(app_id, e))
            return default

    def exists(self, app_id):
        target_path = self._file_path(app_id)
        try:
            os.stat(target_path)
            return True
        except Exception:
            return False

    def is_under_pressure(self, cfg=None, min_block=16384):
        """Return True when total free SRAM < swap_low_sram OR largest contiguous block < min_block."""
        try:
            from core.memutil import heap_pressure
            return heap_pressure(cfg=cfg, min_block=min_block)
        except Exception:
            return False

    def delete(self, app_id):
        target_path = self._file_path(app_id)
        try:
            os.remove(target_path)
            return True
        except Exception:
            return False

    def prune_stale(self, max_age_s=86400, max_files=16):
        """
        Remove orphaned .tmp files, corrupted swap files, files older than max_age_s,
        and excess swap files beyond max_files.
        Returns number of removed files.
        """
        _mkdir_p(self.swap_dir)
        removed = 0
        now_ts = int(time.time())
        valid_entries = []

        try:
            names = os.listdir(self.swap_dir)
        except Exception:
            return 0

        for fn in names:
            full = "{}/{}".format(self.swap_dir, fn)
            # 1. Always remove orphaned temporary files
            if fn.endswith(".tmp"):
                try:
                    os.remove(full)
                    removed += 1
                except Exception:
                    pass
                continue

            if not fn.endswith(".swap.json"):
                continue

            # 2. Inspect swap envelope for corruption or staleness
            try:
                with open(full, "r") as f:
                    env = json.load(f)
                if not isinstance(env, dict) or env.get("magic") != SWAP_MAGIC:
                    raise ValueError("Bad magic")
                payload_json = env.get("payload")
                if not isinstance(payload_json, str) or _checksum32(payload_json) != env.get("checksum"):
                    raise ValueError("Bad checksum")
                ts = int(env.get("ts", 0))
                if max_age_s is not None and max_age_s >= 0 and ts > 0 and now_ts >= ts:
                    if (now_ts - ts) > max_age_s:
                        os.remove(full)
                        removed += 1
                        continue
                valid_entries.append((ts, full))
            except Exception:
                try:
                    os.remove(full)
                    removed += 1
                except Exception:
                    pass

        # 3. Enforce max_files cap (remove oldest first)
        if max_files is not None and len(valid_entries) > int(max_files):
            valid_entries.sort(key=lambda item: item[0])
            excess = len(valid_entries) - int(max_files)
            for _, old_path in valid_entries[:excess]:
                try:
                    os.remove(old_path)
                    removed += 1
                except Exception:
                    pass

        return removed

    def clear_all(self):
        """Delete all files inside /sd/pinhos/.swap/."""
        _mkdir_p(self.swap_dir)
        removed = 0
        try:
            for fn in os.listdir(self.swap_dir):
                try:
                    os.remove("{}/{}".format(self.swap_dir, fn))
                    removed += 1
                except Exception:
                    pass
        except Exception:
            pass
        return removed

    def stats(self, max_kb=None):
        """Return swap usage telemetry: {'files', 'bytes', 'used_kb', 'max_kb', 'pct'}."""
        _mkdir_p(self.swap_dir)
        files = 0
        total_bytes = 0
        try:
            for fn in os.listdir(self.swap_dir):
                if fn.endswith(".swap.json"):
                    files += 1
                    try:
                        st = os.stat("{}/{}".format(self.swap_dir, fn))
                        total_bytes += int(st[6])
                    except Exception:
                        pass
        except Exception:
            pass
        mk = self.max_kb if max_kb is None else max(0, int(max_kb))
        used_kb = (total_bytes + 1023) // 1024 if total_bytes > 0 else 0
        pct = min(100, (total_bytes * 100) // (mk * 1024)) if mk > 0 else 0
        if total_bytes > 0 and pct == 0 and mk > 0:
            pct = 2
        return {"files": files, "bytes": total_bytes, "used_kb": used_kb, "max_kb": mk, "pct": pct}


_default_swap = None


def get_swap_manager(swap_dir=None):
    global _default_swap
    if _default_swap is None or (swap_dir and _default_swap.swap_dir != swap_dir.rstrip("/")):
        _default_swap = SwapManager(swap_dir=swap_dir)
    return _default_swap


def save(app_id, state_dict, swap_dir=None):
    return get_swap_manager(swap_dir).save(app_id, state_dict)


def load(app_id, default=None, swap_dir=None):
    return get_swap_manager(swap_dir).load(app_id, default=default)


def delete(app_id, swap_dir=None):
    return get_swap_manager(swap_dir).delete(app_id)


def prune_stale(max_age_s=86400, max_files=16, swap_dir=None):
    return get_swap_manager(swap_dir).prune_stale(max_age_s=max_age_s, max_files=max_files)


def clear_all(swap_dir=None):
    return get_swap_manager(swap_dir).clear_all()

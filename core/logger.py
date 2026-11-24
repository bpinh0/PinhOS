# PinhOS Phase 1 — Ring-Buffer & SD Diagnostic Logger (core/logger.py)
# Zero hardcoded pin numbers or hardware dependencies.

import os
import sys
import io
import gc
import json
import time

from core.config import PINHOS_ROOT, _mkdir_p, atomic_write_json

LEVEL_DEBUG = 10
LEVEL_INFO  = 20
LEVEL_WARN  = 30
LEVEL_ERROR = 40

_BOOT_ID = None
_BOOT_T0_MS = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _uptime_ms():
    if hasattr(time, "ticks_ms") and hasattr(time, "ticks_diff"):
        return max(0, int(time.ticks_diff(time.ticks_ms(), _BOOT_T0_MS)))
    return max(0, int(time.time() * 1000) - _BOOT_T0_MS)


def get_boot_id(log_dir=None):
    """Return monotonic persisted boot_id (incremented once per boot, cached in module global) (#24)."""
    global _BOOT_ID
    if _BOOT_ID is not None:
        return int(_BOOT_ID)
    p = (log_dir or (PINHOS_ROOT + "/logs")).rstrip("/") + "/boot_id.txt"
    bid = 1
    try:
        with open(p, "r") as f:
            bid = int(f.read().strip()) + 1
    except Exception:
        bid = 1
    try:
        _mkdir_p(log_dir or (PINHOS_ROOT + "/logs"))
        with open(p, "w") as f:
            f.write(str(bid))
    except Exception:
        pass
    _BOOT_ID = bid
    return bid


def _boot_id(log_dir=None):
    return get_boot_id(log_dir)


def _now_str():
    """Format RTC wall-clock; mark unsynced (< 2024) as ~UNSYNCED instead of 2021 dates (#22)."""
    try:
        t = time.localtime()
        if int(t[0]) < 2024:
            return "~UNSYNCED"
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5]
        )
    except Exception:
        return "~UNSYNCED"


def format_log_prefix(log_dir=None):
    """Return unambiguous forensic prefix: [b<boot_id> +<uptime_ms>ms <wall_clock>] (#24)."""
    return "[b{} +{}ms {}]".format(get_boot_id(log_dir), _uptime_ms(), _now_str())


class Logger:
    """
    Bounded in-SRAM ring-buffer logger with persistent SD file output
    and automatic log rotation to preserve SD space and heap memory.
    """

    def __init__(self, log_dir=None, max_ring=40, max_file_bytes=32768):
        self.log_dir = log_dir or (PINHOS_ROOT + "/logs")
        self.sys_log_path = self.log_dir.rstrip("/") + "/system.log"
        self.crash_log_path = self.log_dir.rstrip("/") + "/crash.log"
        self.breadcrumb_path = self.log_dir.rstrip("/") + "/breadcrumb.json"
        self.max_ring = max(8, int(max_ring))
        self.max_file_bytes = max(4096, int(max_file_bytes))
        self._ring = []
        _mkdir_p(self.log_dir)

    def _rotate_if_needed(self, path):
        try:
            st = os.stat(path)
            if st[6] >= self.max_file_bytes:
                bak = path + ".1"
                try:
                    os.remove(bak)
                except Exception:
                    pass
                os.rename(path, bak)
        except Exception:
            pass

    def _append_file(self, path, text):
        try:
            _mkdir_p(self.log_dir)
            self._rotate_if_needed(path)
            with open(path, "a") as f:
                f.write(text)
                if hasattr(f, "flush"):
                    f.flush()
            return True
        except Exception:
            return False

    def log(self, level_tag, msg, persist=True):
        entry = "{} [{}] {}".format(format_log_prefix(self.log_dir), level_tag, str(msg))
        if len(self._ring) >= self.max_ring:
            self._ring.pop(0)
        self._ring.append(entry)
        if persist:
            self._append_file(self.sys_log_path, entry + "\n")
        return entry

    def debug(self, msg, persist=False):
        return self.log("DEBUG", msg, persist=persist)

    def info(self, msg, persist=True):
        return self.log("INFO", msg, persist=persist)

    def warn(self, msg, persist=True):
        return self.log("WARN", msg, persist=persist)

    def error(self, msg, persist=True):
        entry = self.log("ERROR", msg, persist=persist)
        if persist:
            self._append_file(self.crash_log_path, entry + "\n")
        return entry

    def exception(self, context, exc):
        buf = io.StringIO()
        if hasattr(sys, "print_exception"):
            sys.print_exception(exc, buf)
        else:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=buf)
        tb_str = buf.getvalue()
        summary = repr(exc)
        entry = self.log("CRASH", "{}: {}".format(context, summary), persist=True)
        crash_block = (
            "=== PINHOS EXCEPTION [{}] ===\n"
            "Context: {}\n"
            "Fault  : {}\n"
            "{}\n"
        ).format(_now_str(), context, summary, tb_str)
        self._append_file(self.crash_log_path, crash_block)
        return entry

    def get_recent(self, count=20):
        if count <= 0:
            return []
        return list(self._ring[-int(count):])

    def clear_ring(self):
        self._ring.clear()

    # --- Operation Breadcrumbs & Unclean-Shutdown Crash Forensics ---

    def set_breadcrumb(self, op_name, detail=""):
        """Persist current operation breadcrumb so freezes/resets can be diagnosed on next boot."""
        free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        data = {
            "op": str(op_name)[:40],
            "detail": str(detail)[:60],
            "time": _now_str(),
            "free_kb": free_kb,
        }
        return atomic_write_json(self.breadcrumb_path, data)

    def clear_breadcrumb(self, op_name="IDLE"):
        return self.set_breadcrumb(op_name, "")

    def check_previous_crash(self):
        """
        Inspect breadcrumb.json + machine.reset_cause() at boot.
        If the previous run did not reach IDLE/CLEAN_EXIT, record a crash report
        in crash.log and return the forensic dict; otherwise return None.
        """
        rc_str = "BOOT"
        try:
            import machine
            rc = machine.reset_cause()
            rc_names = {1: "PWRON", 2: "HARD_RST", 3: "WDT_TIMEOUT", 4: "WAKE", 5: "SOFT_RST"}
            rc_str = rc_names.get(rc, "RST_" + str(rc))
        except Exception:
            pass

        prev = None
        try:
            with open(self.breadcrumb_path, "r") as f:
                prev = json.load(f)
        except Exception:
            prev = None

        if not isinstance(prev, dict):
            self.clear_breadcrumb("IDLE")
            return None

        prev_op = str(prev.get("op", "IDLE"))
        if prev_op in ("IDLE", "CLEAN_EXIT", ""):
            return None

        prev_detail = str(prev.get("detail", ""))
        prev_time = str(prev.get("time", "unknown"))
        prev_kb = int(prev.get("free_kb", 0))
        report = {
            "op": prev_op,
            "detail": prev_detail,
            "time": prev_time,
            "free_kb": prev_kb,
            "reset_cause": rc_str,
        }
        msg = "UNCLEAN SHUTDOWN in {} ({}) @ {} [{} | {}KB]".format(
            prev_op, prev_detail or "n/a", prev_time, rc_str, prev_kb
        )
        self.log("CRASH", msg, persist=True)
        block = (
            "=== PINHOS UNCLEAN SHUTDOWN / FREEZE [{}] ===\n"
            "Last Op : {} ({})\n"
            "Op Time : {}\n"
            "Cause   : {} | Free SRAM: {} KB\n\n"
        ).format(_now_str(), prev_op, prev_detail or "n/a", prev_time, rc_str, prev_kb)
        self._append_file(self.crash_log_path, block)
        self.clear_breadcrumb("IDLE")
        return report

    def read_tail(self, kind="system", max_lines=60, max_bytes=4096):
        """
        Memory-safe tail reader for system.log or crash.log.
        Reads at most max_bytes from the end of the file to protect RP2350 SRAM.
        """
        path = self.crash_log_path if kind == "crash" else self.sys_log_path
        try:
            st = os.stat(path)
            size = int(st[6])
            if size <= 0:
                return []
            with open(path, "r") as f:
                if size > max_bytes:
                    f.seek(size - max_bytes)
                    # Discard partial first line after seek
                    f.readline()
                raw = f.read()
            lines = [ln.rstrip("\r") for ln in raw.split("\n") if ln.strip()]
            return lines[-int(max_lines):]
        except Exception:
            if kind == "system" and self._ring:
                return list(self._ring[-int(max_lines):])
            return []

    def clear_logs(self, kind="all"):
        targets = []
        if kind in ("all", "system"):
            targets.append(self.sys_log_path)
            self._ring.clear()
        if kind in ("all", "crash"):
            targets.append(self.crash_log_path)
        for p in targets:
            try:
                with open(p, "w") as f:
                    f.write("")
            except Exception:
                pass
        return True


_default_logger = None


def get_logger(log_dir=None):
    global _default_logger
    if _default_logger is None or (log_dir and _default_logger.log_dir != log_dir):
        _default_logger = Logger(log_dir=log_dir)
    return _default_logger

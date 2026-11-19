# PinhOS Phase 1 — Ring-Buffer & SD Diagnostic Logger (core/logger.py)
# Zero hardcoded pin numbers or hardware dependencies.

import os
import sys
import io
import time

from core.config import PINHOS_ROOT, _mkdir_p

LEVEL_DEBUG = 10
LEVEL_INFO  = 20
LEVEL_WARN  = 30
LEVEL_ERROR = 40


def _now_str():
    try:
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5]
        )
    except Exception:
        return "2026-01-01 00:00:00"


class Logger:
    """
    Bounded in-SRAM ring-buffer logger with persistent SD file output
    and automatic log rotation to preserve SD space and heap memory.
    """

    def __init__(self, log_dir=None, max_ring=40, max_file_bytes=32768):
        self.log_dir = log_dir or (PINHOS_ROOT + "/logs")
        self.sys_log_path = self.log_dir.rstrip("/") + "/system.log"
        self.crash_log_path = self.log_dir.rstrip("/") + "/crash.log"
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
        ts = _now_str()
        entry = "[{}] [{}] {}".format(ts, level_tag, str(msg))
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


_default_logger = None


def get_logger(log_dir=None):
    global _default_logger
    if _default_logger is None or (log_dir and _default_logger.log_dir != log_dir):
        _default_logger = Logger(log_dir=log_dir)
    return _default_logger

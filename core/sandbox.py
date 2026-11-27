# PinhOS Phase 1 — Sandboxed App Runner (core/sandbox.py)
# Enforces APP_META contract without top-level execution, gates on min_sram,
# tracks file/socket handles, purges imported modules, restores HAL state, and runs GC.

import sys
import gc
import json

try:
    import builtins
except Exception:
    try:
        import __builtin__ as builtins
    except Exception:
        builtins = None

REQUIRED_META_KEYS = (
    "id",
    "name",
    "version",
    "category",
    "entry",
    "min_sram",
    "ui_modes",
)


class SandboxError(Exception):
    """Base exception for sandboxed app validation and execution errors."""
    pass


class SandboxMetaError(SandboxError):
    """Raised when APP_META is missing, malformed, or violates the schema contract."""
    pass


class SandboxMemoryError(SandboxError):
    """Raised when free SRAM is below the app's declared min_sram requirement."""
    pass


class SandboxAbort(SandboxError):
    """Raised when an unresponsive app is force-closed by the user/OS ANR dialog."""
    pass


class SandboxPolicyError(SandboxError):
    """Raised when an app violates the PinhOS App Contract or calls forbidden OS-breaking APIs."""
    pass


VALID_UI_MODES = ("gui", "tui", "native")

# Forbidden tokens in untrusted apps (apps/*.py): blocked statically BEFORE compile/import
FORBIDDEN_APP_TOKENS = (
    ("machine.Pin", "Direct GPIO (machine.Pin) forbidden; use ctx.board HAL"),
    ("from machine import Pin", "Direct GPIO (Pin) forbidden; use ctx.board HAL"),
    ("machine.WDT", "Direct WDT access forbidden; OS manages watchdog"),
    ("machine.reset(", "machine.reset() forbidden in apps"),
    ("machine.soft_reset(", "machine.soft_reset() forbidden in apps"),
    ("machine.deepsleep(", "machine.deepsleep() forbidden in apps"),
    ("os.dupterm(", "os.dupterm() forbidden in apps (breaks COM4)"),
    ("stopRefresh(", "stopRefresh() forbidden (wedges RP2350 Core 1)"),
    ("recoverRefresh(", "recoverRefresh() forbidden (wedges RP2350 Core 1)"),
    ("poll_input(", "board.poll_input() returns int; use board.poll_key()"),
    ("__pinhos_wdt__", "Internal __pinhos_wdt__ forbidden; use ctx.yield_()"),
    ("_pinhos_main", "Internal _pinhos_main access forbidden in apps"),
)


def _strip_comment(line):
    in_q = None
    esc = False
    for i, ch in enumerate(line):
        if in_q is not None:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_q:
                in_q = None
        else:
            if ch in ('"', "'"):
                in_q = ch
            elif ch == "#":
                return line[:i]
    return line


def _validate_meta_strict(meta):
    aid = meta.get("id", "")
    if len(aid) < 2 or len(aid) > 24 or not ("a" <= aid[0] <= "z"):
        raise SandboxPolicyError("APP_META['id'] must be 2-24 chars [a-z0-9_], starting with a-z")
    for ch in aid:
        if not (("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "_"):
            raise SandboxPolicyError("APP_META['id'] has invalid char '{}'; use [a-z0-9_]".format(ch))
    if meta.get("min_sram", 0) < 16384:
        raise SandboxPolicyError("APP_META['min_sram'] must be >= 16384 for apps")
    if "min_block" in meta:
        mb = meta["min_block"]
        if not isinstance(mb, int) or isinstance(mb, bool) or mb < 0:
            raise SandboxPolicyError("APP_META['min_block'] must be a non-negative integer")
    for m in meta.get("ui_modes", []):
        if m not in VALID_UI_MODES:
            raise SandboxPolicyError("Invalid ui_mode '{}'; use gui/tui/native".format(m))


def _scan_policy_lines(lines_iter):
    for lineno, raw in enumerate(lines_iter, 1):
        code = _strip_comment(raw)
        if not code.strip():
            continue
        for tok, reason in FORBIDDEN_APP_TOKENS:
            if tok in code:
                raise SandboxPolicyError("L{}: {}".format(lineno, reason))


def get_free_sram():
    """Return free heap bytes in MicroPython (or a 256 KB baseline on standard CPython)."""
    gc.collect()
    if hasattr(gc, "mem_free"):
        return int(gc.mem_free())
    return 262144


def _extract_dict_block(source, var_name="APP_META"):
    """
    Locate `APP_META = { ... }` in source text and extract the balanced `{ ... }` block
    without executing any code.
    """
    lines = source.split("\n")
    start_idx = -1
    pos = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(var_name):
            rest = stripped[len(var_name):].lstrip()
            if rest.startswith("="):
                brace_pos = line.find("{", line.find("="))
                if brace_pos != -1:
                    start_idx = pos + brace_pos
                else:
                    start_idx = pos + line.find("=") + 1
                break
        pos += len(line) + 1

    if start_idx == -1:
        raise SandboxMetaError("Missing top-level {} assignment".format(var_name))

    # Advance to opening '{'
    n = len(source)
    i = start_idx
    while i < n and source[i] != "{":
        if not source[i].isspace() and source[i] != "#":
            if source[i] == "\n":
                pass
            else:
                raise SandboxMetaError("{} must be assigned a dict literal".format(var_name))
        if source[i] == "#":
            while i < n and source[i] != "\n":
                i += 1
        else:
            i += 1

    if i >= n or source[i] != "{":
        raise SandboxMetaError("Could not find opening '{{' for {}".format(var_name))

    brace_start = i
    depth = 0
    in_str = None
    escaped = False

    while i < n:
        ch = source[i]
        if in_str is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'"):
                in_str = ch
            elif ch == "#":
                while i < n and source[i] != "\n":
                    i += 1
                continue
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[brace_start:i + 1]
        i += 1

    raise SandboxMetaError("Unclosed '{{' in {} definition".format(var_name))


def _py_dict_literal_to_json(raw_block):
    """
    Convert a safe Python dictionary literal string into strict JSON string
    without invoking eval() or exec().
    """
    out = []
    n = len(raw_block)
    i = 0
    in_str = None
    escaped = False

    while i < n:
        ch = raw_block[i]
        if in_str is not None:
            if escaped:
                if ch == "'":
                    out.append("'")
                else:
                    out.append("\\" + ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                out.append('"')
                in_str = None
            else:
                if ch == '"' and in_str == "'":
                    out.append('\\"')
                else:
                    out.append(ch)
            i += 1
            continue

        # Outside string literal
        if ch == "#":
            while i < n and raw_block[i] != "\n":
                i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            out.append('"')
            i += 1
            continue
        if ch == "(":
            out.append("[")
            i += 1
            continue
        if ch == ")":
            out.append("]")
            i += 1
            continue

        # Handle Python keywords True, False, None and numeric underscores
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (raw_block[j].isalpha() or raw_block[j].isdigit() or raw_block[j] == "_"):
                j += 1
            word = raw_block[i:j]
            if word == "True":
                out.append("true")
            elif word == "False":
                out.append("false")
            elif word == "None":
                out.append("null")
            else:
                raise SandboxMetaError("Disallowed identifier in APP_META: {}".format(word))
            i = j
            continue

        if ch.isdigit():
            j = i
            while j < n and (raw_block[j].isdigit() or raw_block[j] == "_"):
                if raw_block[j] != "_":
                    out.append(raw_block[j])
                j += 1
            i = j
            continue

        out.append(ch)
        i += 1

    # Remove trailing commas before '}' or ']'
    cleaned = "".join(out)
    final_chars = []
    m = len(cleaned)
    k = 0
    in_jstr = False
    jesc = False
    while k < m:
        c = cleaned[k]
        if in_jstr:
            final_chars.append(c)
            if jesc:
                jesc = False
            elif c == "\\":
                jesc = True
            elif c == '"':
                in_jstr = False
            k += 1
            continue
        if c == '"':
            in_jstr = True
            final_chars.append(c)
            k += 1
            continue
        if c == ",":
            look = k + 1
            while look < m and cleaned[look].isspace():
                look += 1
            if look < m and cleaned[look] in ("}", "]"):
                k += 1
                continue
        final_chars.append(c)
        k += 1

    return "".join(final_chars)


def _has_entry_function(source, entry_name):
    target = "def " + str(entry_name) + "("
    for line in source.split("\n"):
        s = line.strip()
        if s.startswith(target) or s.startswith("def " + str(entry_name) + " ("):
            return True
    return False


def parse_app_meta(source, strict=False):
    """
    Statically parse and validate APP_META from Python source string without
    executing any top-level application code.
    """
    if not isinstance(source, str) or not source.strip():
        raise SandboxMetaError("App source is empty")

    raw_block = _extract_dict_block(source, "APP_META")
    json_str = _py_dict_literal_to_json(raw_block)
    try:
        meta = json.loads(json_str)
    except Exception as e:
        raise SandboxMetaError("Malformed APP_META literal: {}".format(e))

    if not isinstance(meta, dict):
        raise SandboxMetaError("APP_META must be a dictionary")

    for req_key in REQUIRED_META_KEYS:
        if req_key not in meta:
            raise SandboxMetaError("APP_META missing required key: '{}'".format(req_key))

    for str_key in ("id", "name", "version", "category", "entry"):
        val = meta.get(str_key)
        if not isinstance(val, str) or not val.strip():
            raise SandboxMetaError("APP_META['{}'] must be a non-empty string".format(str_key))

    min_sram = meta.get("min_sram")
    if not isinstance(min_sram, int) or isinstance(min_sram, bool) or min_sram < 0:
        raise SandboxMetaError("APP_META['min_sram'] must be a non-negative integer")

    ui_modes = meta.get("ui_modes")
    if not isinstance(ui_modes, list) or not ui_modes:
        raise SandboxMetaError("APP_META['ui_modes'] must be a non-empty list")
    for mode in ui_modes:
        if not isinstance(mode, str) or not mode.strip():
            raise SandboxMetaError("APP_META['ui_modes'] entries must be strings")

    if not _has_entry_function(source, meta["entry"]):
        raise SandboxMetaError(
            "App does not define declared entry function 'def {}(ctx):'".format(meta["entry"])
        )

    if strict:
        _validate_meta_strict(meta)
        _scan_policy_lines(source.split("\n"))

    return meta


def inspect_app(app_path, strict=None):
    """
    Stream-read only the header of an app file (<= 1.5 KB) to statically validate
    APP_META, then scan line-by-line for the entry function and (for apps) OS safety policy.
    """
    if strict is None:
        p = str(app_path or "").replace("\\", "/")
        strict = not ("/tools/" in p or p.startswith("tools/"))
    try:
        with open(app_path, "r") as f:
            head = f.read(1536)
    except Exception as e:
        raise SandboxMetaError("Cannot read app file '{}': {}".format(app_path, e))

    if not isinstance(head, str) or not head.strip():
        raise SandboxMetaError("App source is empty")

    raw_block = _extract_dict_block(head, "APP_META")
    json_str = _py_dict_literal_to_json(raw_block)
    try:
        meta = json.loads(json_str)
    except Exception as e:
        raise SandboxMetaError("Malformed APP_META literal: {}".format(e))

    if not isinstance(meta, dict):
        raise SandboxMetaError("APP_META must be a dictionary")
    for req_key in REQUIRED_META_KEYS:
        if req_key not in meta:
            raise SandboxMetaError("APP_META missing required key: '{}'".format(req_key))
    for str_key in ("id", "name", "version", "category", "entry"):
        val = meta.get(str_key)
        if not isinstance(val, str) or not val.strip():
            raise SandboxMetaError("APP_META['{}'] must be a non-empty string".format(str_key))
    min_sram = meta.get("min_sram")
    if not isinstance(min_sram, int) or isinstance(min_sram, bool) or min_sram < 0:
        raise SandboxMetaError("APP_META['min_sram'] must be a non-negative integer")
    ui_modes = meta.get("ui_modes")
    if not isinstance(ui_modes, list) or not ui_modes:
        raise SandboxMetaError("APP_META['ui_modes'] must be a non-empty list")

    if strict:
        _validate_meta_strict(meta)

    entry_name = meta["entry"]
    found_entry = _has_entry_function(head, entry_name)
    if strict or not found_entry:
        t1 = "def " + str(entry_name) + "("
        t2 = "def " + str(entry_name) + " ("
        try:
            with open(app_path, "r") as f:
                lineno = 0
                for line in f:
                    lineno += 1
                    s = line.strip()
                    if not found_entry and (s.startswith(t1) or s.startswith(t2)):
                        found_entry = True
                    if strict:
                        code = _strip_comment(line)
                        if code.strip():
                            for tok, reason in FORBIDDEN_APP_TOKENS:
                                if tok in code:
                                    raise SandboxPolicyError("L{}: {}".format(lineno, reason))
                    elif found_entry:
                        break
        except SandboxPolicyError:
            raise
        except Exception as e:
            raise SandboxMetaError("Cannot scan app file '{}': {}".format(app_path, e))
    if not found_entry:
        raise SandboxMetaError(
            "App does not define declared entry function 'def {}(ctx):'".format(entry_name)
        )
    return meta


class _TrackedHandle:
    """Proxy wrapper around an open file, socket, or hardware peripheral handle."""

    def __init__(self, raw_handle, tracker, kind="file"):
        self._raw = raw_handle
        self._tracker = tracker
        self.kind = kind
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            raw = self._raw
            self._raw = None
            if raw is not None:
                try:
                    if hasattr(raw, "close"):
                        raw.close()
                    elif hasattr(raw, "deinit"):
                        raw.deinit()
                except Exception:
                    pass
            if self._tracker is not None:
                self._tracker._untrack(self)

    def deinit(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __iter__(self):
        if self._raw is None:
            return iter(())
        return iter(self._raw)

    def _feed_wdt(self):
        if builtins is not None:
            _w = sys.modules.get("__pinhos_wdt__")
            if _w is not None:
                try:
                    _w.feed()
                except Exception:
                    pass

    def read(self, *args, **kwargs):
        if self.closed or self._raw is None:
            raise ValueError("I/O operation on closed handle")
        self._feed_wdt()
        return self._raw.read(*args, **kwargs)

    def readline(self, *args, **kwargs):
        if self.closed or self._raw is None:
            raise ValueError("I/O operation on closed handle")
        self._feed_wdt()
        return self._raw.readline(*args, **kwargs)

    def write(self, *args, **kwargs):
        if self.closed or self._raw is None:
            raise ValueError("I/O operation on closed handle")
        self._feed_wdt()
        return self._raw.write(*args, **kwargs)

    def __getattr__(self, name):
        if self.closed or self._raw is None:
            raise ValueError("I/O operation on closed handle")
        return getattr(self._raw, name)


class ResourceTracker:
    """Tracks all file, socket, and peripheral handles opened during sandbox execution."""

    def __init__(self, real_open):
        self._real_open = real_open
        self._handles = []

    def track(self, raw_handle, kind="resource"):
        if isinstance(raw_handle, _TrackedHandle):
            return raw_handle
        wrapped = _TrackedHandle(raw_handle, self, kind=kind)
        self._handles.append(wrapped)
        return wrapped

    def _untrack(self, wrapped):
        try:
            self._handles.remove(wrapped)
        except ValueError:
            pass

    def open(self, file, mode="r", *args, **kwargs):
        raw = self._real_open(file, mode, *args, **kwargs)
        return self.track(raw, kind="file")

    def socket(self, *args, **kwargs):
        import socket as _sock_mod
        raw_sock = _sock_mod.socket(*args, **kwargs)
        return self.track(raw_sock, kind="socket")

    def close_all(self):
        """Force-close all remaining open handles and return the count of leaked handles."""
        leaked = list(self._handles)
        self._handles.clear()
        closed_count = 0
        for h in leaked:
            if not h.closed:
                h.close()
                closed_count += 1
        return closed_count


class AppContext:
    """Runtime context passed to sandboxed `main(ctx)` entry points."""

    def __init__(self, meta, board=None, config=None, swap=None, logger=None, tracker=None, args=None, theme=None, ui=None):
        self.meta = meta
        self.app_id = meta.get("id", "unknown")
        self.board = board
        self.config = config
        self.swap = swap
        self.logger = logger
        self.theme = theme
        self.ui = ui
        self._tracker = tracker
        self.args = args or {}

    def open(self, file, mode="r", *args, **kwargs):
        if self._tracker is not None:
            return self._tracker.open(file, mode, *args, **kwargs)
        return open(file, mode, *args, **kwargs)

    def socket(self, *args, **kwargs):
        if self._tracker is not None:
            return self._tracker.socket(*args, **kwargs)
        import socket as _sock_mod
        return _sock_mod.socket(*args, **kwargs)

    def track(self, handle, kind="resource"):
        if self._tracker is not None:
            return self._tracker.track(handle, kind=kind)
        return handle

    def save_state(self, state_dict):
        if self.swap is not None:
            return self.swap.save(self.app_id, state_dict)
        return False

    def load_state(self, default=None):
        if self.swap is not None:
            return self.swap.load(self.app_id, default=default)
        return default

    def log(self, msg):
        """Append a compact diagnostic note to this app's dedicated /sd/pinhos/logs/app_<id>.log."""
        if self.logger is not None and hasattr(self.logger, "app_note"):
            try:
                return self.logger.app_note(self.app_id, msg, kind="NOTE")
            except Exception:
                pass
        return None

    def yield_(self, step_web=True):
        """Cooperative yield for long-running tools: feeds hardware WDT and steps WebPortal/CYW43."""
        if builtins is not None:
            _w = sys.modules.get("__pinhos_wdt__")
            if _w is not None:
                try:
                    _w.feed()
                except Exception:
                    pass
        if step_web:
            m = sys.modules.get("main") or sys.modules.get("_pinhos_main")
            if m is not None and hasattr(m, "step_webportal"):
                try:
                    m.step_webportal(0)
                except Exception:
                    pass


class SandboxRunner:
    """
    Isolated application runner enforcing:
    1. Static APP_META validation without top-level execution.
    2. Pre-launch gc.mem_free() >= min_sram gate.
    3. sys.modules snapshot and file/socket handle tracking.
    4. Guaranteed finally: cleanup (handle closure, module purge, HAL restore, GC).
    """

    def __init__(self, board=None, config=None, swap=None, logger=None, theme=None, ui=None):
        self.board = board
        self.config = config
        self.swap = swap
        self.logger = logger
        self.theme = theme
        self.ui = ui

    def inspect(self, app_path):
        return inspect_app(app_path)

    def show_recovery_screen(self, app_id, error_str, sram_delta=0, wait_key=True):
        """
        Render Sandbox fault recovery screen and poll board.poll_key() in a
        non-blocking loop until Enter/Esc/Q dismisses the dialog.
        """
        if self.board is None:
            return None
        try:
            b = self.board
            if hasattr(b, "init_uart_bridge"):
                try:
                    b.init_uart_bridge(rebind=True)
                except Exception:
                    pass
            b.recover_refresh()
            b.fill(0)
            b.rect(4, 4, 312, 312, 9)
            b.fill_rect(6, 6, 308, 26, 9)
            b.text("!! SANDBOX APP FAULT ISOLATED !!", 28, 15, 15)
            b.text("APP ID     : {}".format(str(app_id)[:24]), 14, 48, 3)
            b.text("SRAM DELTA : {} B (RECLAIMED)".format(int(sram_delta)), 14, 66, 10)
            try:
                gc.collect()
                _fk = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 0
                try:
                    from core.memutil import largest_free
                    _bk = largest_free(cap=98304) // 1024
                except Exception:
                    _bk = _fk
                _hc = 9 if _bk < 20 else (3 if _fk < 48 else 10)
                b.text("HEAP       : {}K free | {}K blk".format(_fk, _bk), 14, 84, _hc)
            except Exception:
                pass
            b.text("EXCEPTION  :", 14, 106, 3)
            err = str(error_str or "Unknown error")
            b.text(err[:36], 14, 124, 15)
            if len(err) > 36:
                b.text(err[36:72], 14, 140, 15)
            if len(err) > 72:
                b.text(err[72:108], 14, 156, 15)
            b.text("Log: app_{}.log (^L Logs)".format(str(app_id)[:16]), 14, 248, 6)
            b.fill_rect(10, 276, 300, 30, 8)
            b.rect(10, 276, 300, 30, 3)
            b.text("[ENTER / ESC / Q] Return to OS", 34, 287, 15)
            b.show()

            if wait_key:
                import time
                b.clear_input()
                while True:
                    poll_fn = getattr(b, "poll_key", None) or getattr(b, "read_key", None)
                    k = poll_fn() if poll_fn else None
                    if k:
                        ku = str(k).upper()
                        if ku in ("ENTER", "ESC", "Q", "SPACE", " ", "BACKSPACE", "BACK"):
                            b.beep(1100, 12)
                            return ku
                    if hasattr(time, "sleep_ms"):
                        time.sleep_ms(30)
                    else:
                        time.sleep(0.03)
        except KeyboardInterrupt:
            raise
        except Exception:
            pass
        return None

    def _prompt_anr(self, app_id, reason="App not responding", poll_fn=None):
        """Android-style 'App Not Responding' dialog: [W/ENT] Keep Waiting or [K/ESC] Force Close."""
        b = self.board
        if b is None:
            return "kill"
        try:
            import time
            b.fill_rect(14, 78, 292, 152, 0)
            b.rect(14, 78, 292, 152, 11)
            b.fill_rect(16, 80, 288, 22, 11)
            b.text("!! APP NOT RESPONDING !!", 48, 87, 0)
            b.text("App : {}".format(str(app_id)[:28]), 24, 112, 15)
            b.text("Why : {}".format(str(reason)[:28]), 24, 128, 6)
            b.hline(20, 146, 280, 11)
            b.text("[W / ENT] Keep Waiting", 24, 158, 10)
            b.text("[K / ESC] Force Close App", 24, 178, 9)
            b.hline(20, 200, 280, 11)
            b.text("OS remains safe; RAM reclaimed", 24, 210, 6)
            b.show()
            b.clear_input()
            pf = poll_fn or getattr(b, "poll_key", None) or getattr(b, "read_key", None)
            _wd = sys.modules.get("__pinhos_wdt__")
            while True:
                if _wd is not None:
                    try:
                        _wd.feed()
                    except Exception:
                        pass
                k = pf() if pf else None
                if k:
                    ku = str(k).upper()
                    if ku in ("W", "ENTER", "RETURN", "SPACE", " "):
                        b.beep(1300, 12)
                        return "wait"
                    if ku in ("K", "ESC", "Q", "BACK", "BACKSPACE", "A"):
                        b.beep(900, 15)
                        return "kill"
                if hasattr(time, "sleep_ms"):
                    time.sleep_ms(30)
                else:
                    time.sleep(0.03)
        except KeyboardInterrupt:
            return "kill"
        except Exception:
            return "kill"

    def _should_purge_mod(self, mod_name):
        """Purge only applet/tool modules — never clear core/net/ui/boards/web singletons (#16)."""
        for keep_pre in ("core", "net", "ui", "boards", "web", "tests", "asyncio", "uasyncio"):
            if mod_name == keep_pre or mod_name.startswith(keep_pre + "."):
                return False
        return True

    def _exec_sandboxed(self, meta, invoke_cb, app_path="<sandbox_app>", args=None, wait_on_error=False, mod_name=None):
        """Unified sandbox lifecycle for run_source() and run_file() (#6, #12, #16)."""
        app_id = meta["id"]
        min_sram = int(meta["min_sram"])
        _ws = getattr(builtins, "_pinhos_web_srv", None) if builtins is not None else None
        _paused_web = False
        if meta.get("needs_radio") and _ws is not None and hasattr(_ws, "pause") and not getattr(_ws, "_paused", False):
            try:
                _paused_web = bool(_ws.pause())
            except Exception:
                _paused_web = False
        web_up = bool(_ws is not None and not _paused_web)
        sram_floor = max(min_sram, 49152 if web_up else 32768)

        try:
            gc.collect()
            free_before = get_free_sram()
            if free_before < sram_floor:
                raise SandboxMemoryError(
                    "App '{}' needs {}K free SRAM, only {}K free".format(
                        app_id, sram_floor // 1024, free_before // 1024
                    )
                )
            min_block = int(meta.get("min_block", 16384))
            if min_block > 0:
                try:
                    from core.memutil import largest_free
                    blk = largest_free(cap=max(min_block, 16384))
                    if blk < min_block:
                        raise SandboxMemoryError(
                            "App '{}' needs {}K blk, only {}K blk ({}K free)".format(
                                app_id, min_block // 1024, blk // 1024, free_before // 1024
                            )
                        )
                except ImportError:
                    pass
        except SandboxMemoryError:
            if _paused_web and _ws is not None and hasattr(_ws, "resume"):
                try:
                    _ws.resume()
                except Exception:
                    pass
            raise

        modules_before = set(sys.modules.keys())
        if mod_name and mod_name in sys.modules:
            sys.modules.pop(mod_name, None)
            modules_before.discard(mod_name)
        real_open = open
        tracker = ResourceTracker(real_open)
        ctx = AppContext(
            meta=meta, board=self.board, config=self.config, swap=self.swap,
            logger=self.logger, tracker=tracker, args=args, theme=self.theme, ui=self.ui,
        )

        hooked_builtins = False
        if builtins is not None and hasattr(builtins, "open"):
            try:
                setattr(builtins, "open", tracker.open)
                hooked_builtins = True
            except Exception:
                hooked_builtins = False

        ret_val, err_str, ok, aborted = None, None, False, False
        leaked_closed = 0
        purged_modules = []
        # Wrap board.poll_key to (1) feed WDT on every poll and (2) intercept ALT+F5 ANR/Force-Close
        _orig_poll = None
        _bd = self.board
        _wd = sys.modules.get("__pinhos_wdt__")
        if _wd is not None and hasattr(_wd, "set_op"):
            try:
                _wd.set_op("APP:" + str(app_id)[:24])
            except Exception:
                pass
        if _bd is not None and hasattr(_bd, "poll_key"):
            try:
                _orig_poll = _bd.poll_key
                _self = self
                _aid = app_id

                def _wpoll(_o=_orig_poll, _w=_wd, _b=_bd, _s=_self, _a=_aid):
                    if _w is not None:
                        try:
                            _w.feed()
                        except Exception:
                            pass
                    k = _o()
                    if k and str(k).upper() == "F5":
                        try:
                            if _b.get_modifiers() & 4:  # MOD_ALT = 4
                                if _s._prompt_anr(_a, "Force-check (ALT+F5)", poll_fn=_o) == "kill":
                                    raise SandboxAbort("Force-closed by user")
                                return None
                        except SandboxAbort:
                            raise
                        except Exception:
                            pass
                    return k
                _bd.poll_key = _wpoll
            except Exception:
                _orig_poll = None
        try:
            ret_val = invoke_cb(ctx, tracker)
            ok = True
        except KeyboardInterrupt:
            err_str = "Interrupted (Ctrl-C)"
            ok = False
        except SandboxAbort as ab_exc:
            err_str = str(ab_exc)
            ok = False
            aborted = True
            if self.logger is not None and hasattr(self.logger, "app_note"):
                try:
                    self.logger.app_note(app_id, err_str, kind="ABORT")
                except Exception:
                    pass
        except (Exception, MemoryError) as exc:
            if type(exc).__name__ == "SoftWatchdogAbort":
                err_str = str(exc) or "ANR: Aborted by Soft WDT"
                ok = False
                aborted = True
                if self.logger is not None and hasattr(self.logger, "app_note"):
                    try:
                        self.logger.app_note(app_id, err_str, kind="ANR")
                    except Exception:
                        pass
            else:
                err_str = repr(exc)
                if self.logger is not None:
                    try:
                        if hasattr(self.logger, "app_exception"):
                            self.logger.app_exception(app_id, exc)
                        else:
                            self.logger.exception("SANDBOX({})".format(app_id), exc)
                    except Exception:
                        pass
            exc = None
        finally:
            if _wd is not None and hasattr(_wd, "set_op"):
                try:
                    _wd.set_op("IDLE")
                except Exception:
                    pass
            if _orig_poll is not None:
                try:
                    _bd.poll_key = _orig_poll
                except Exception:
                    pass
            if hooked_builtins and builtins is not None:
                try:
                    setattr(builtins, "open", real_open)
                except Exception:
                    pass
            leaked_closed = tracker.close_all()
            for mn in list(sys.modules.keys()):
                if mn not in modules_before and self._should_purge_mod(mn):
                    purged_modules.append(mn)
                    try:
                        mo = sys.modules.pop(mn, None)
                        if mo is not None and hasattr(mo, "__dict__"):
                            mo.__dict__.clear()
                    except Exception:
                        pass
            ctx._tracker = ctx.board = ctx.config = ctx.swap = ctx.logger = ctx.theme = ctx.ui = None
            ctx = tracker = None
            if self.board is not None:
                try:
                    self.board.restore_state()
                except Exception:
                    pass
            if _paused_web and _ws is not None and hasattr(_ws, "resume"):
                try:
                    _ws.resume()
                except Exception:
                    pass
            gc.collect()
            gc.collect()

        free_after = get_free_sram()
        sram_delta = max(0, free_before - free_after)
        if not ok and not aborted and wait_on_error:
            self.show_recovery_screen(app_id, err_str, sram_delta=sram_delta, wait_key=True)
        return {
            "ok": ok, "aborted": aborted, "app_id": app_id, "meta": meta, "return_value": ret_val,
            "error": err_str, "leaked_handles_closed": leaked_closed,
            "purged_modules": purged_modules, "sram_before": free_before,
            "sram_after": free_after, "sram_delta": sram_delta,
        }

    def run_source(self, source, app_path="<sandbox_app>", args=None, wait_on_error=False):
        meta = parse_app_meta(source)
        app_id = meta["id"]
        entry_name = meta["entry"]

        def _invoke(ctx, tracker):
            app_globals = {
                "__name__": "__sandbox_{}__".format(app_id),
                "__file__": app_path,
                "open": tracker.open,
            }
            try:
                code_obj = compile(source, app_path, "exec")
                exec(code_obj, app_globals)
                code_obj = None
                entry_fn = app_globals.get(entry_name)
                if not callable(entry_fn):
                    raise SandboxMetaError("Entry point '{}' in '{}' is not callable".format(entry_name, app_id))
                return entry_fn(ctx)
            finally:
                try:
                    app_globals.clear()
                except Exception:
                    pass

        return self._exec_sandboxed(meta, _invoke, app_path=app_path, args=args, wait_on_error=wait_on_error)

    def run_file(self, app_path, args=None, wait_on_error=False):
        """
        Execute an app file inside the sandbox. When app_path lives under /sd/pinhos/
        (e.g. tools/*.py or apps/*.py), streams compilation via MicroPython's native
        file-backed import instead of slurping the full source string into SRAM.
        """
        gc.collect()
        meta = inspect_app(app_path)
        app_id = meta["id"]
        entry_name = meta["entry"]

        mod_name = None
        if isinstance(app_path, str) and app_path.startswith("/sd/pinhos/") and app_path.endswith(".py"):
            rel = app_path[len("/sd/pinhos/"):-3]
            if rel and "/" in rel:
                mod_name = rel.replace("/", ".")

        if mod_name is None:
            try:
                with open(app_path, "r") as f:
                    source = f.read()
            except Exception as e:
                raise SandboxError("Cannot read app '{}': {}".format(app_path, e))
            return self.run_source(source, app_path=app_path, args=args, wait_on_error=wait_on_error)

        def _invoke(ctx, _tracker):
            mod = __import__(mod_name, None, None, ("*",))
            entry_fn = getattr(mod, entry_name, None)
            if not callable(entry_fn):
                raise SandboxMetaError("Entry '{}' in '{}' not callable".format(entry_name, app_id))
            return entry_fn(ctx)

        return self._exec_sandboxed(meta, _invoke, app_path=app_path, args=args, wait_on_error=wait_on_error, mod_name=mod_name)

# PinhOS Phase 3 — Built-In BusyBox Shell (tools/shell.py)
# Compact RP2350-tuned BusyBox CLI (<20KB): quote-aware lexer, ';', '|', '>'/'>>',
# 20-entry history ring, tab-completion, bounded 53-col scrollback, <=1KB streaming FS
# commands, and on-demand system/hardware commands (tools/_shell_cmds.py).

APP_META = {
    "id": "busybox_shell",
    "name": "BusyBox Shell",
    "version": "1.0.0",
    "category": "Field Tools",
    "description": "Interactive BusyBox CLI with pipes, redirects, history & field cmds",
    "entry": "main",
    "min_sram": 40960,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}

import os
import gc
import time

HOME = "/sd/pinhos"
CHUNK = 1024
COLS = 53
HIST_MAX = 20
PROTECTED = ("/", "/sd", "/flash", "/sd/pinhos", "/boot.py", "/main.py")
_READERS = ("cat", "head", "tail", "grep", "wc", "hexdump", "hd", "cp", "mv")


class ShellError(Exception):
    pass


class ShellInterrupt(Exception):
    pass


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else (a - b)


def _sleep_ms(ms):
    time.sleep_ms(int(ms)) if hasattr(time, "sleep_ms") else time.sleep(ms / 1000.0)


def abspath(cwd, p):
    if not p:
        return cwd
    if p[0] != "/":
        p = cwd.rstrip("/") + "/" + p
    parts = []
    for s in p.split("/"):
        if not s or s == ".":
            continue
        if s == "..":
            if parts:
                parts.pop()
        else:
            parts.append(s)
    return "/" + "/".join(parts)


def join(a, b):
    return a.rstrip("/") + "/" + b


def basename(p):
    return p.rstrip("/").rpartition("/")[2] or "/"


def stat_of(p):
    try:
        return os.stat(p)
    except OSError:
        return None


def is_dir(p):
    st = stat_of(p)
    return st is not None and bool(st[0] & 0x4000)


def hsize(n):
    if n < 1024:
        return "{}B".format(n)
    for u in ("K", "M", "G"):
        n = n / 1024.0
        if n < 1024 or u == "G":
            return "{:.1f}{}".format(n, u) if n < 10 else "{}{}".format(int(n), u)
    return str(n)


def clean(s):
    if "\t" in s:
        s = s.replace("\t", "    ")
    if "\r" in s:
        s = s.replace("\r", "")
    for c in s:
        if c < " " or c > "~":
            return "".join([x if " " <= x <= "~" else "." for x in s])
    return s


def dec(b):
    if b[-1:] == b"\r":
        b = b[:-1]
    try:
        return b.decode()
    except Exception:
        return "".join([chr(c) if 32 <= c < 127 else "." for c in b])


def close_gen(g):
    c = getattr(g, "close", None)
    if c:
        try:
            c()
        except Exception:
            pass


def iter_lines(path, tick=None):
    f = open(path, "rb")
    try:
        carry = b""
        while True:
            ch = f.read(CHUNK)
            if not ch:
                break
            parts = (carry + ch).split(b"\n")
            carry = parts.pop()
            for p in parts:
                yield dec(p)
            if len(carry) >= CHUNK:
                yield dec(carry)
                carry = b""
            if tick:
                tick()
        if carry:
            yield dec(carry)
    finally:
        f.close()


def read_tail(path, n, max_bytes=16384, tick=None):
    if n <= 0:
        return []
    try:
        size = os.stat(path)[6]
    except OSError:
        return []
    if size <= 0:
        return []
    f = open(path, "rb")
    try:
        pos, data = size, b""
        while pos > 0 and len(data) < max_bytes:
            step = CHUNK if pos >= CHUNK else pos
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
            if data.count(b"\n") > n:
                break
            if tick:
                tick()
    finally:
        f.close()
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if pos > 0 and lines:
        lines = lines[1:]
    return [dec(x) for x in lines[-n:]]


def format_columns(names, cols=COLS):
    if not names:
        return []
    w = max(len(x) for x in names) + 2
    per = max(1, cols // w)
    return ["".join([x + " " * (w - len(x)) for x in names[i:i + per]]).rstrip() for i in range(0, len(names), per)]


def _expand(line, i, getenv):
    n, j = len(line), i + 1
    if j < n and line[j] == "?":
        return getenv("?"), j + 1
    if j < n and line[j] == "{":
        k = line.find("}", j)
        if k < 0:
            raise ShellError("bad ${...}")
        return getenv(line[j + 1:k]), k + 1
    k = j
    while k < n and (line[k].isalpha() or line[k].isdigit() or line[k] == "_"):
        k += 1
    return ("$", j) if k == j else (getenv(line[j:k]), k)


def tokenize(line, getenv=None):
    if getenv is None:
        getenv = lambda _k: ""
    toks, cur, has, i, n = [], [], False, 0, len(line)
    while i < n:
        c = line[i]
        if c == "'":
            j = line.find("'", i + 1)
            if j < 0:
                raise ShellError("unterminated '")
            cur.append(line[i + 1:j]); has = True; i = j + 1
        elif c == '"':
            i += 1; closed = False
            while i < n:
                c = line[i]
                if c == '"':
                    closed = True; i += 1; break
                if c == "\\" and i + 1 < n and line[i + 1] in '"\\$':
                    cur.append(line[i + 1]); i += 2
                elif c == "$":
                    s, i = _expand(line, i, getenv); cur.append(s)
                else:
                    cur.append(c); i += 1
            if not closed:
                raise ShellError('unterminated "')
            has = True
        elif c == "\\" and i + 1 < n:
            cur.append(line[i + 1]); has = True; i += 2
        elif c == "$":
            s, i = _expand(line, i, getenv)
            if s:
                cur.append(s); has = True
        elif c in " \t":
            if has:
                toks.append(("w", "".join(cur))); cur = []; has = False
            i += 1
        elif c in ";|>":
            if has:
                toks.append(("w", "".join(cur))); cur = []; has = False
            if c == ">" and line[i + 1:i + 2] == ">":
                toks.append(("o", ">>")); i += 2
            else:
                toks.append(("o", c)); i += 1
        elif c == "#" and not has:
            break
        else:
            cur.append(c); has = True; i += 1
    if has:
        toks.append(("w", "".join(cur)))
    return toks


def parse(toks):
    pipes, stages, argv, redir, i, n = [], [], [], None, 0, len(toks)
    while i < n:
        k, v = toks[i]; i += 1
        if k == "w":
            argv.append(v)
        elif v in (">", ">>"):
            if i >= n or toks[i][0] != "w" or redir is not None:
                raise ShellError("syntax: redirect")
            redir = (v, toks[i][1]); i += 1
        else:
            if not argv:
                raise ShellError("syntax near " + v)
            stages.append({"argv": argv, "redir": redir}); argv = []; redir = None
            if v == ";":
                pipes.append(stages); stages = []
    if argv:
        stages.append({"argv": argv, "redir": redir})
    elif redir or stages:
        raise ShellError("syntax error")
    if stages:
        pipes.append(stages)
    for st in pipes:
        for k in range(len(st) - 1):
            if st[k]["redir"]:
                raise ShellError("redirect before pipe")
    return pipes


class Scrollback:
    def __init__(self, cols=COLS, max_lines=140):
        self.cols, self.max_lines, self.lines = cols, max_lines, []

    def add(self, text, tag=" "):
        text = clean(str(text))
        if not text:
            if len(self.lines) >= self.max_lines:
                self.lines.pop(0)
            self.lines.append(tag)
            return
        for i in range(0, len(text), self.cols):
            if len(self.lines) >= self.max_lines:
                self.lines.pop(0)
            self.lines.append(tag + text[i:i + self.cols])

    def clear(self):
        del self.lines[:]


class LineInput:
    def __init__(self, hist_max=HIST_MAX):
        self.buf = ""; self.pos = 0; self.hist = []; self.hist_max = hist_max
        self._hidx = -1; self._draft = ""

    def insert(self, s):
        self.buf = self.buf[:self.pos] + s + self.buf[self.pos:]; self.pos += len(s); self._hidx = -1

    def backspace(self):
        if self.pos > 0:
            self.buf = self.buf[:self.pos - 1] + self.buf[self.pos:]; self.pos -= 1; self._hidx = -1

    def delete(self):
        if self.pos < len(self.buf):
            self.buf = self.buf[:self.pos] + self.buf[self.pos + 1:]; self._hidx = -1

    def left(self):
        if self.pos > 0:
            self.pos -= 1

    def right(self):
        if self.pos < len(self.buf):
            self.pos += 1

    def home(self):
        self.pos = 0

    def end(self):
        self.pos = len(self.buf)

    def clear(self):
        self.buf = ""; self.pos = 0; self._hidx = -1

    def push_history(self, line):
        if line.strip() and (not self.hist or self.hist[-1] != line):
            self.hist.append(line)
            while len(self.hist) > self.hist_max:
                self.hist.pop(0)
        self._hidx = -1

    def prev(self):
        if not self.hist:
            return False
        if self._hidx == -1:
            self._draft = self.buf; self._hidx = len(self.hist) - 1
        elif self._hidx > 0:
            self._hidx -= 1
        else:
            return False
        self.buf = self.hist[self._hidx]; self.pos = len(self.buf); return True

    def next(self):
        if self._hidx == -1:
            return False
        if self._hidx < len(self.hist) - 1:
            self._hidx += 1; self.buf = self.hist[self._hidx]
        else:
            self._hidx = -1; self.buf = self._draft
        self.pos = len(self.buf); return True

    def submit(self):
        ln = self.buf; self.push_history(ln); self.buf = ""; self.pos = 0; return ln


def opts(args, valued="", cmd=""):
    fl, pos, i, n = {}, [], 0, len(args)
    while i < n:
        a = args[i]; i += 1
        if a == "--":
            pos.extend(args[i:]); break
        if len(a) > 1 and a[0] == "-":
            body = a[1:]
            if body.isdigit():
                fl["n"] = body; continue
            j = 0
            while j < len(body):
                ch = body[j]; j += 1
                if ch in valued:
                    v = body[j:]
                    if not v:
                        if i >= n:
                            raise ShellError("{}: -{} needs value".format(cmd, ch))
                        v = args[i]; i += 1
                    fl[ch] = v; break
                fl[ch] = True
        else:
            pos.append(a)
    return fl, pos


def int_opt(fl, key, default, cmd):
    if key not in fl:
        return default
    try:
        return int(fl[key])
    except ValueError:
        raise ShellError("{}: bad int '{}'".format(cmd, fl[key]))


def _unwrap(it):
    for x in it:
        yield x[1] if isinstance(x, tuple) else x


class Shell:
    Error = ShellError
    opts = staticmethod(opts)
    int_opt = staticmethod(int_opt)
    read_tail = staticmethod(read_tail)

    def __init__(self, board=None, config=None, logger=None, theme_mgr=None, ui=None, cwd=HOME, app_id="busybox_shell"):
        self.board, self.config, self.logger = board, config, logger
        self.theme_mgr, self.ui, self.app_id = theme_mgr, ui, app_id
        self.cwd = cwd if is_dir(cwd) else "/"
        self.oldpwd = self.cwd
        self.env = {"HOME": HOME, "USER": "pinh", "SHELL": "busybox"}
        self.status = 0; self.rc_hint = None; self.exit_requested = False
        self.scrollback = Scrollback()
        self.line = LineInput()
        self.interrupt_cb = None; self.on_output = None
        self.handlers = {}; self.out = self._sb_out; self._ticks = 0
        self.commands = dict(COMMANDS)
        try:
            from tools._shell_cmds import SYS_COMMANDS
            self.commands.update(SYS_COMMANDS)
        except Exception:
            pass

    def getenv(self, k):
        return str(self.status) if k == "?" else (self.cwd if k == "PWD" else self.env.get(k, ""))

    def path(self, p):
        return abspath(self.cwd, HOME + p[1:] if (p == "~" or p.startswith("~/")) else p)

    def prompt(self):
        c = self.cwd if len(self.cwd) <= 22 else ".../" + basename(self.cwd)
        return c + "$ "

    def _sb_out(self, text, tag=" "):
        self.scrollback.add(text, tag)
        if self.on_output:
            self.on_output()

    def tick(self):
        self._ticks += 1
        if (self._ticks & 7) == 0 and self.interrupt_cb and self.interrupt_cb():
            raise ShellInterrupt()

    def complete(self, line, pos):
        head = line[:pos]; i = len(head)
        while i > 0 and head[i - 1] not in " \t;|>":
            i -= 1
        word, before = head[i:], head[:i].rstrip()
        if (before == "" or before[-1] in ";|") and "/" not in word:
            cands = sorted([c for c in self.commands if c.startswith(word)]); dp = ""
        else:
            d, sep, base = word.rpartition("/")
            dp = "/" if (sep and not d) else ((d + "/") if sep else "")
            tgt = self.path(dp) if dp else self.cwd
            try:
                nms = os.listdir(tgt)
            except OSError:
                nms = []
            cands = sorted([nm + "/" if is_dir(join(tgt, nm)) else nm for nm in nms if nm.startswith(base)])
        if not cands:
            return line, pos, []
        if len(cands) == 1:
            nw = dp + cands[0] + ("" if cands[0].endswith("/") else " ")
        else:
            a, b = min(cands), max(cands); k = 0
            while k < len(a) and k < len(b) and a[k] == b[k]:
                k += 1
            nw = dp + a[:k] if len(dp + a[:k]) > len(word) else word
        return line[:i] + nw + line[pos:], i + len(nw), (cands if len(cands) > 1 else [])

    def view(self, nrows, cols, scroll):
        lines, pr = self.scrollback.lines, self.prompt()
        full, ct = pr + self.line.buf, len(pr) + self.line.pos
        start = max(0, ct - (cols - 1))
        prow, lead = "p" + full[start:start + cols], max(0, len(pr) - start)
        tot = len(lines) + 1
        scroll = min(scroll, max(0, tot - nrows))
        end = tot - scroll; beg = max(0, end - nrows); nl = len(lines)
        rows = [prow if i == nl else lines[i] for i in range(beg, end)]
        return rows, ((len(rows) - 1, ct - start) if scroll == 0 else None), lead, scroll

    def submit(self, line):
        self.scrollback.add(self.prompt() + line, "c")
        return self.run_line(line) if line.strip() else self.status

    def run_line(self, line, out=None):
        o = out or self.out
        try:
            pipes = parse(tokenize(line, self.getenv))
        except ShellError as e:
            o("sh: " + str(e), "e"); self.status = 2; return 2
        for stages in pipes:
            self.status = self._run_pipe(stages, o)
            if self.exit_requested or self.status == 130:
                break
        gc.collect()
        return self.status

    def _run_pipe(self, stages, out):
        rc, gens, name = 0, [], ""
        self.rc_hint = None
        try:
            last = stages[-1]
            if last["redir"]:
                tgt = self.path(last["redir"][1])
                for st in stages:
                    if st["argv"][0] in _READERS and any(w[:1] != "-" and self.path(w) == tgt for w in st["argv"][1:]):
                        raise ShellError("input is output")
            stream = None
            for idx, st in enumerate(stages):
                name = st["argv"][0]
                fn = self.commands.get(name)
                if fn is None:
                    raise ShellError(name + ": not found")
                if idx > 0 and stream is not None:
                    stream = _unwrap(stream)
                    gens.append(stream)
                stream = fn(self, st["argv"][1:], stream) or ()
                gens.append(stream)
            if last["redir"]:
                mode, target = last["redir"]
                p = self.path(target)
                if is_dir(p):
                    raise ShellError(target + ": is a directory")
                with open(p, "w" if mode == ">" else "a") as f:
                    for item in stream:
                        f.write((item[1] if isinstance(item, tuple) else item) + "\n")
                        self.tick()
            else:
                for item in stream:
                    out(item[1], item[0]) if isinstance(item, tuple) else out(item, " ")
                    self.tick()
            if self.rc_hint is not None:
                rc = self.rc_hint
        except (ShellInterrupt, KeyboardInterrupt):
            out("^C", "w"); rc = 130
        except ShellError as e:
            out(str(e), "e"); rc = 1
        except OSError as e:
            out("{}: OSError {}".format(name, e.args[0] if e.args else e), "e"); rc = 1
        except Exception as e:
            out("{}: {!r}".format(name, e), "e"); rc = 1
        finally:
            for g in gens:
                close_gen(g)
        return rc

    def need_file(self, cmd, arg):
        p = self.path(arg); st = stat_of(p)
        if st is None:
            raise ShellError("{}: {}: No such file or directory".format(cmd, arg))
        if st[0] & 0x4000:
            raise ShellError("{}: {}: Is a directory".format(cmd, arg))
        return p

    def log_path(self, kind):
        lg = self.logger
        if kind == "crash":
            return lg.crash_log_path if lg else HOME + "/logs/crash.log"
        return lg.sys_log_path if lg else HOME + "/logs/system.log"


# --- Core FS Commands ---

def _ls_gen(sh, targets, lng, allf):
    for t in targets:
        p = sh.path(t); st = stat_of(p)
        if st is None:
            raise ShellError("ls: {}: No such file".format(t))
        if not (st[0] & 0x4000):
            yield ("- {:>6} {}".format(hsize(st[6]), t) if lng else t); continue
        ents = sorted([(e[0], e[1] == 0x4000) for e in os.ilistdir(p) if allf or e[0][:1] != "."])
        if lng:
            for nm, isd in ents:
                s2 = stat_of(join(p, nm))
                if s2:
                    yield ("c" if isd else " ", "{} {:>6} {}{}".format("d" if isd else "-", hsize(s2[6]), nm, "/" if isd else ""))
        else:
            for r in format_columns([nm + "/" if isd else nm for nm, isd in ents]):
                yield r
        if not ents:
            yield ("m", "(empty)")


def cmd_ls(sh, a, inp):
    fl, pos = opts(a, "", "ls")
    return _ls_gen(sh, pos or ["."], "l" in fl, "a" in fl)


def cmd_cd(sh, a, inp):
    t = sh.oldpwd if (a and a[0] == "-") else (a[0] if a else HOME)
    p = sh.path(t)
    if not is_dir(p):
        raise ShellError("cd: {}: Not a directory".format(t))
    sh.oldpwd, sh.cwd = sh.cwd, p


def _srcs(sh, cmd, files, inp):
    if files:
        for f in files:
            yield f, iter_lines(sh.need_file(cmd, f), sh.tick)
    elif inp is not None:
        yield "(stdin)", inp
    else:
        raise ShellError(cmd + ": missing file")


def cmd_cat(sh, a, inp):
    fl, pos = opts(a, "", "cat"); num = "n" in fl
    def _g():
        n = 0
        for _, it in _srcs(sh, "cat", pos, inp):
            for ln in it:
                n += 1; yield "{:>5} {}".format(n, ln) if num else ln
    return _g()


def cmd_head(sh, a, inp):
    fl, pos = opts(a, "n", "head"); n = int_opt(fl, "n", 10, "head")
    def _g():
        for _, it in _srcs(sh, "head", pos, inp):
            c = 0
            for ln in it:
                if c >= n:
                    break
                yield ln; c += 1
            close_gen(it)
    return _g()


def cmd_tail(sh, a, inp):
    fl, pos = opts(a, "n", "tail"); n = min(500, int_opt(fl, "n", 10, "tail"))
    def _g():
        if pos:
            for f in pos:
                for ln in read_tail(sh.need_file("tail", f), n, tick=sh.tick):
                    yield ln
        elif inp is not None:
            ring = []
            for ln in inp:
                ring.append(ln)
                if len(ring) > n:
                    ring.pop(0)
            for ln in ring:
                yield ln
        else:
            raise ShellError("tail: missing file")
    return _g()


def cmd_grep(sh, a, inp):
    fl, pos = opts(a, "", "grep")
    if not pos:
        raise ShellError("grep: PAT [FILE...]")
    pat, files = pos[0], pos[1:]
    ic, num, inv, cnt = "i" in fl, "n" in fl, "v" in fl, "c" in fl
    nd = pat.lower() if ic else pat
    def _g():
        hits = 0
        for lbl, it in _srcs(sh, "grep", files, inp):
            n = c = 0
            for ln in it:
                n += 1
                if (nd in (ln.lower() if ic else ln)) != inv:
                    c += 1
                    if not cnt:
                        yield ("{}:".format(n) if num else "") + ln
                sh.tick()
            hits += c
            if cnt:
                yield str(c)
        if hits == 0:
            sh.rc_hint = 1
    return _g()


def cmd_wc(sh, a, inp):
    fl, pos = opts(a, "", "wc")
    wl, ww, wc = "l" in fl, "w" in fl, "c" in fl
    if not (wl or ww or wc):
        wl = ww = wc = True
    def fmt(l, w, c, lbl):
        p = ([str(l)] if wl else []) + ([str(w)] if ww else []) + ([str(c)] if wc else [])
        return " ".join(["{:>6}".format(x) for x in p]) + ((" " + lbl) if lbl else "")
    def _g():
        if pos:
            for fn in pos:
                p = sh.need_file("wc", fn); l = w = c = 0; inw = False
                with open(p, "rb") as f:
                    while True:
                        ch = f.read(CHUNK)
                        if not ch:
                            break
                        c += len(ch); l += ch.count(b"\n"); pts = ch.split(); w += len(pts)
                        if inw and pts and ch[0] not in b" \t\r\n":
                            w -= 1
                        inw = ch[-1] not in b" \t\r\n"; sh.tick()
                yield fmt(l, w, c, fn)
        elif inp is not None:
            l = w = c = 0
            for ln in inp:
                l += 1; w += len(ln.split()); c += len(ln) + 1
            yield fmt(l, w, c, "")
    return _g()


def cmd_mkdir(sh, a, inp):
    fl, pos = opts(a, "", "mkdir")
    if not pos:
        raise ShellError("mkdir: missing operand")
    for t in pos:
        p = sh.path(t)
        if "p" in fl:
            cur = ""
            for s in p.split("/"):
                if s:
                    cur += "/" + s
                    if not is_dir(cur):
                        os.mkdir(cur)
        else:
            os.mkdir(p)


def _guard(cmd, p):
    pp = p.rstrip("/") or "/"
    if pp in PROTECTED:
        raise ShellError("{}: refusing to modify protected '{}'".format(cmd, pp))


def _rm_tree(sh, p):
    for nm in os.listdir(p):
        c = join(p, nm)
        _rm_tree(sh, c) if is_dir(c) else os.remove(c)
        sh.tick()
    os.rmdir(p)


def cmd_rm(sh, a, inp):
    fl, pos = opts(a, "", "rm"); rec = "r" in fl or "R" in fl; frc = "f" in fl
    if not pos:
        raise ShellError("rm: missing operand")
    for t in pos:
        p = sh.path(t); _guard("rm", p); st = stat_of(p)
        if st is None:
            if not frc:
                raise ShellError("rm: {}: No such file".format(t))
        elif st[0] & 0x4000:
            if not rec:
                raise ShellError("rm: {}: Is a directory".format(t))
            _rm_tree(sh, p)
        else:
            os.remove(p)


def _cp_file(sh, s, d):
    with open(s, "rb") as fi:
        with open(d, "wb") as fo:
            while True:
                b = fi.read(CHUNK)
                if not b:
                    break
                fo.write(b); sh.tick()


def cmd_cp(sh, a, inp):
    fl, pos = opts(a, "", "cp")
    if len(pos) < 2:
        raise ShellError("cp: SRC DST")
    dst = sh.path(pos[-1]); isd = is_dir(dst)
    for s in pos[:-1]:
        sp = sh.path(s)
        _cp_file(sh, sp, join(dst, basename(sp)) if isd else dst)


def cmd_mv(sh, a, inp):
    if len(a) < 2:
        raise ShellError("mv: SRC DST")
    dst = sh.path(a[-1]); isd = is_dir(dst)
    for s in a[:-1]:
        sp = sh.path(s); _guard("mv", sp)
        d = join(dst, basename(sp)) if isd else dst
        try:
            os.rename(sp, d)
        except OSError:
            _cp_file(sh, sp, d); os.remove(sp)


def cmd_hexdump(sh, a, inp):
    fl, pos = opts(a, "ns", "hexdump")
    if not pos:
        raise ShellError("hexdump: FILE")
    p = sh.need_file("hexdump", pos[0])
    skip, lim = int_opt(fl, "s", 0, "hexdump"), int_opt(fl, "n", 256, "hexdump")
    def _g():
        with open(p, "rb") as f:
            if skip:
                f.seek(skip)
            off, rem = skip, lim
            while rem > 0:
                ch = f.read(min(CHUNK, rem))
                if not ch:
                    break
                for i in range(0, len(ch), 8):
                    r = ch[i:i + 8]
                    yield "{:06x}: {:<23} |{}|".format(
                        off + i, " ".join(["{:02x}".format(c) for c in r]),
                        "".join([chr(c) if 32 <= c < 127 else "." for c in r]))
                off += len(ch); rem -= len(ch); sh.tick()
    return _g()


def cmd_edit(sh, a, inp):
    if not a:
        raise ShellError("edit: FILE")
    h = sh.handlers.get("edit")
    if not h:
        raise ShellError("edit: no UI")
    msg = h(sh.path(a[0]))
    return (msg,) if msg else None


def cmd_help(sh, a, inp):
    nms = sorted(sh.commands)
    return [("c", "PinhOS BusyBox sh ({} cmds)".format(len(nms)))] + format_columns(nms)


COMMANDS = {
    "ls": cmd_ls, "ll": lambda sh, a, i: cmd_ls(sh, ["-l"] + list(a), i),
    "pwd": lambda sh, a, i: (sh.cwd,), "cd": cmd_cd,
    "echo": lambda sh, a, i: (" ".join(a[1:] if (a and a[0] == "-n") else a),),
    "cat": cmd_cat, "head": cmd_head, "tail": cmd_tail, "grep": cmd_grep, "wc": cmd_wc,
    "mkdir": cmd_mkdir, "rm": cmd_rm, "rmdir": lambda sh, a, i: ([_guard("rmdir", sh.path(t)) or os.rmdir(sh.path(t)) for t in a] and None),
    "cp": cmd_cp, "mv": cmd_mv,
    "touch": lambda sh, a, i: ([open(sh.path(t), "a").close() for t in a if stat_of(sh.path(t)) is None] and None),
    "hexdump": cmd_hexdump, "hd": cmd_hexdump, "edit": cmd_edit, "nano": cmd_edit,
    "clear": lambda sh, a, i: sh.scrollback.clear(), "cls": lambda sh, a, i: sh.scrollback.clear(),
    "exit": lambda sh, a, i: setattr(sh, "exit_requested", True),
    "quit": lambda sh, a, i: setattr(sh, "exit_requested", True),
    "history": lambda sh, a, i: ["{:>3} {}".format(k + 1, l) for k, l in enumerate(sh.line.hist)],
    "env": lambda sh, a, i: ["{}={}".format(k, sh.env[k]) for k in sorted(sh.env)] + ["PWD=" + sh.cwd],
    "help": cmd_help,
}


def main(ctx):
    board, ui = ctx.board, ctx.ui
    if board is None or ui is None:
        return {"error": "no board/ui"}
    from ui.widgets import StatusBar, FooterBar, TermView, layout_term_screen
    try:
        from boards.base import MOD_CTRL, MOD_SHIFT
    except Exception:
        MOD_CTRL, MOD_SHIFT = 2, 1

    sh = Shell(board=board, config=ctx.config, logger=ctx.logger, theme_mgr=ctx.theme, ui=ui, app_id=ctx.app_id)
    scroll, last_draw, mode_seen = [0], [0], [None]
    hints = "TAB:Cmp ^C:Cancel F3:Mode F4:Theme ESC:Exit"
    sb = StatusBar(0, 0, 320, 20, title="BusyBox sh", mode_label=ui.mode_badge)
    tv = TermView()
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=hints)

    def mount():
        ui.clear_widgets(); ui.add_widget(sb); ui.add_widget(tv); ui.add_widget(fb); ui.set_focus(tv)
        mode_seen[0] = ui.mode; layout_term_screen(ui.mode, sb, tv, fb); ui.mark_all_dirty(True)

    def refresh(force=False):
        if ui.mode != mode_seen[0]:
            mode_seen[0] = ui.mode; layout_term_screen(ui.mode, sb, tv, fb); ui.mark_all_dirty(True)
        geom = ui.backend.term_metrics(tv)
        rows, cur, lead, sc = sh.view(geom[4], geom[3], scroll[0])
        scroll[0] = sc; tv.lead_cols = lead; tv.set_rows(rows, cur)
        rk = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        sb.update(mode_label=ui.mode_badge)
        fb.update(status=("SCROLL -{} ln".format(sc) if sc else "{} | {}K | rc={}".format(sh.cwd[-22:], rk, sh.status)),
                  status_kind="warn" if sc else ("ok" if sh.status == 0 else "err"), hints=hints)
        ui.render(force=force); last_draw[0] = _ticks_ms()

    def open_ed(path):
        from tools.editor import Editor
        ed = Editor(board, ui, path, logger=ctx.logger)
        try:
            return ed.run()
        finally:
            ed = None; board.clear_input(); mount(); gc.collect()

    def _flush_out():
        scroll[0] = 0
        refresh()

    def _on_out():
        if _ticks_diff(_ticks_ms(), last_draw[0]) >= 80:
            scroll[0] = 0
            refresh()

    sh.interrupt_cb = lambda: (lambda k: k == "ESC" or (k and len(k) == 1 and k in "cC" and bool(board.get_modifiers() & MOD_CTRL)))(board.poll_key())
    sh.on_output = _on_out
    sh.handlers["edit"] = open_ed
    sh.handlers["flush"] = _flush_out

    try:
        sh.scrollback.add("PinhOS BusyBox sh (type 'help')", "c")
        mount(); board.clear_input(); refresh(force=True)
        idle = 0
        while not sh.exit_requested:
            k = board.poll_key()
            if k is None:
                idle += 1
                if idle >= 60:
                    idle = 0; gc.collect()
                _sleep_ms(30); continue
            idle = 0; mods = board.get_modifiers(); ctrl = bool(mods & MOD_CTRL); shift = bool(mods & MOD_SHIFT)
            li = sh.line; pg = max(1, ui.backend.term_metrics(tv)[4] // 2)
            if (ctrl and len(k) == 1 and k.upper() == "P") or getattr(board, "pending_screenshot", None):
                from ui.menu import show_screenshot_toast
                show_screenshot_toast(board, ui, fb)
                refresh(force=True)
                continue
            if ctrl and len(k) == 1:
                c = k.upper()
                if c == "C":
                    sh.scrollback.add(sh.prompt() + li.buf + "^C", "w"); li.clear(); scroll[0] = 0
                elif c == "L":
                    sh.scrollback.clear(); scroll[0] = 0
                elif c == "A":
                    li.home()
                elif c == "E":
                    li.end()
                elif c == "D":
                    li.delete() if li.buf else setattr(sh, "exit_requested", True)
            elif k == "ENTER":
                scroll[0] = 0; sh.submit(li.submit()); gc.collect()
            elif k == "BACKSPACE":
                li.backspace(); scroll[0] = 0
            elif k == "LEFT":
                li.home() if shift else li.left()
            elif k == "RIGHT":
                li.end() if shift else li.right()
            elif k == "UP":
                if shift:
                    scroll[0] += pg
                else:
                    li.prev(); scroll[0] = 0
            elif k == "DOWN":
                if shift:
                    scroll[0] = max(0, scroll[0] - pg)
                else:
                    li.next(); scroll[0] = 0
            elif k == "TAB":
                nl, np_, cands = sh.complete(li.buf, li.pos)
                if nl != li.buf:
                    li.buf, li.pos = nl, np_
                elif cands:
                    sh.scrollback.add(sh.prompt() + li.buf, "c")
                    for r in format_columns(cands):
                        sh.scrollback.add(r, "m")
                scroll[0] = 0
            elif k == "ESC":
                li.clear() if li.buf else setattr(sh, "exit_requested", True)
            elif k == "F3":
                ui.toggle_mode(persist=True)
            elif k == "F4":
                ui.cycle_theme(step=1, persist=True)
            elif k == "SPACE":
                li.insert(" "); scroll[0] = 0
            elif len(k) == 1 and " " <= k <= "~":
                li.insert(k); scroll[0] = 0
            if not sh.exit_requested:
                refresh()
        return {"history": len(sh.line.hist), "status": sh.status}
    finally:
        sh.handlers.clear(); sh.scrollback.clear(); sh.interrupt_cb = sh.on_output = None
        ui.clear_widgets(); gc.collect()

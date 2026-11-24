# PinhOS Phase 3 — On-Device Text / Config Editor (tools/editor.py)
# Lightweight nano-style line editor for /sd/pinhos/config.json, scripts & logs.
# Streams in <=1 KB chunks, caps editable RAM at 16 KB (larger files open read-only),
# validates .json before saving, and runs cleanly inside SandboxRunner or tools/shell.py.

APP_META = {
    "id": "text_editor",
    "name": "Text Editor",
    "version": "1.0.0",
    "category": "Field Tools",
    "description": "Streaming on-device text/JSON editor with search, cut/paste & JSON check",
    "entry": "main",
    "min_sram": 40960,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}

import gc
import os
import time

try:
    from boards.base import MOD_CTRL, MOD_SHIFT
except Exception:
    MOD_CTRL, MOD_SHIFT = 2, 1

MAX_EDIT_BYTES = 16384
CHUNK = 1024
GUTTER = 5
TAB_WIDTH = 4


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _basename(p):
    return p.rstrip("/").rpartition("/")[2] or "/"


def _clean(s):
    if "\r" in s:
        s = s.replace("\r", "")
    for ch in s:
        if ch < " " or ch > "~":
            return "".join([c if " " <= c <= "~" else "." for c in s])
    return s


def _decode_safe(raw):
    try:
        return raw.decode()
    except Exception:
        buf = bytearray(raw)
        for i in range(len(buf)):
            c = buf[i]
            if c < 32 or c >= 127:
                buf[i] = 46
        return buf.decode("ascii")


def _iter_lines(path, limit=None):
    f = open(path, "rb")
    try:
        carry = b""
        done = 0
        while True:
            want = CHUNK if limit is None else min(CHUNK, limit - done)
            if want <= 0:
                break
            ch = f.read(want)
            if not ch:
                break
            done += len(ch)
            parts = (carry + ch).split(b"\n")
            carry = parts.pop()
            for p in parts:
                if p[-1:] == b"\r":
                    p = p[:-1]
                yield _decode_safe(p)
            if len(carry) >= CHUNK:
                yield _decode_safe(carry)
                carry = b""
        if carry:
            if carry[-1:] == b"\r":
                carry = carry[:-1]
            yield _decode_safe(carry)
    finally:
        f.close()


class Editor:
    def __init__(self, board, ui, path, logger=None):
        self.board = board
        self.ui = ui
        self.path = path
        self.logger = logger
        self.lines = [""]
        self.cy = 0
        self.cx = 0
        self.top = 0
        self.hoff = 0
        self.modified = False
        self.readonly = False
        self.clip = None
        self.last_find = ""
        self.status = ""
        self.status_kind = "info"
        self.mode = "edit"  # edit | find | goto | confirm
        self._pbuf = ""
        self._json_warned = False
        self._result = None
        self.sb = self.tv = self.fb = None
        self._mode_seen = None

    def load(self):
        try:
            st = os.stat(self.path)
        except OSError:
            self._set("[New] " + _basename(self.path), "ok")
            return
        size = st[6]
        limit = MAX_EDIT_BYTES if size > MAX_EDIT_BYTES else None
        ro_reason = None
        if limit is not None:
            self.readonly = True
            ro_reason = "READ-ONLY: {}B > 16KB cap".format(size)
        else:
            try:
                from core.memutil import largest_free
                need = max(16384, min(MAX_EDIT_BYTES, size) + 4096)
                blk = largest_free(cap=max(need, 16384))
                if blk < need:
                    self.readonly = True
                    limit = min(size, max(2048, blk // 2))
                    ro_reason = "READ-ONLY: low contig RAM ({}KB)".format(blk // 1024)
            except Exception:
                pass
        lines = []
        for ln in _iter_lines(self.path, limit=limit):
            if "\t" in ln:
                ln = ln.replace("\t", " " * TAB_WIDTH)
            lines.append(ln)
        if self.readonly and lines and limit is not None and size > limit:
            lines.pop()
        self.lines = lines or [""]
        if self.readonly:
            self._set(ro_reason or "READ-ONLY", "warn")
        else:
            self._set("Loaded {} lines".format(len(self.lines)), "info")

    def save(self):
        if self.readonly:
            self._set("Read-only (>16KB)", "err")
            return False
        if self.path.endswith(".json") and not self._json_warned:
            try:
                import json
                json.loads("\n".join(self.lines))
            except Exception:
                self._json_warned = True
                self._set("INVALID JSON! ^S again to force", "err")
                return False
        tmp = self.path + ".tmp"
        try:
            f = open(tmp, "w")
            try:
                if not (len(self.lines) == 1 and self.lines[0] == ""):
                    buf, n = [], 0
                    for ln in self.lines:
                        buf.append(ln); buf.append("\n")
                        n += len(ln) + 1
                        if n >= 512:
                            f.write("".join(buf))
                            buf, n = [], 0
                    if buf:
                        f.write("".join(buf))
            finally:
                f.close()
            try:
                os.remove(self.path)
            except OSError:
                pass
            os.rename(tmp, self.path)
        except OSError as e:
            self._set("Save err: {}".format(e), "err")
            return False
        self.modified = False
        self._json_warned = False
        if self.logger is not None:
            try:
                self.logger.info("EDIT: saved {} ({} ln)".format(self.path, len(self.lines)))
            except Exception:
                pass
        self._set("Saved {} lines".format(len(self.lines)), "ok")
        return True

    def _set(self, text, kind="info"):
        self.status = text
        self.status_kind = kind

    def _mount(self):
        from ui.widgets import StatusBar, FooterBar, TermView, layout_term_screen
        ui = self.ui
        self.sb = StatusBar(0, 0, 320, 20, title="edit", mode_label=ui.mode_badge)
        self.tv = TermView()
        self.tv.lead_token = "text_muted"
        self.tv.lead_cols = GUTTER
        self.fb = FooterBar(0, 276, 320, 44, status="", status_kind="info",
                            hints="^S:Save ^X:Exit ^F:Find ^G:Goto ^K:Cut ^U:Paste")
        ui.clear_widgets()
        ui.add_widget(self.sb)
        ui.add_widget(self.tv)
        ui.add_widget(self.fb)
        ui.set_focus(self.tv)
        self._mode_seen = ui.mode
        layout_term_screen(ui.mode, self.sb, self.tv, self.fb)
        ui.mark_all_dirty(True)

    def refresh(self, force=False):
        from ui.widgets import layout_term_screen
        ui = self.ui
        if ui.mode != self._mode_seen:
            self._mode_seen = ui.mode
            layout_term_screen(ui.mode, self.sb, self.tv, self.fb)
            ui.mark_all_dirty(True)
        geom = ui.backend.term_metrics(self.tv)
        cols, nrows = geom[3], geom[4]
        tcols = cols - GUTTER
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + nrows:
            self.top = self.cy - nrows + 1
        if self.cx < self.hoff:
            self.hoff = max(0, self.cx - 8)
        elif self.cx >= self.hoff + tcols:
            self.hoff = self.cx - tcols + 8

        rows = []
        end = min(len(self.lines), self.top + nrows)
        for i in range(self.top, end):
            rows.append("p{:>4} {}".format(i + 1, _clean(self.lines[i][self.hoff:self.hoff + tcols])))
        while len(rows) < nrows:
            rows.append("m   ~")
        cur = (self.cy - self.top, GUTTER + self.cx - self.hoff) if self.mode == "edit" else None
        self.tv.set_rows(rows, cur)

        self.sb.update(
            title="edit {}{}".format(_basename(self.path), " *" if self.modified else ""),
            mode_label=ui.mode_badge,
            right_text="L{}:C{}{}".format(self.cy + 1, self.cx + 1, " RO" if self.readonly else ""),
        )
        if self.mode == "find":
            self.fb.update(status="Find: {}_".format(self._pbuf), status_kind="info", hints="ENTER:Next ESC:Cancel")
        elif self.mode == "goto":
            self.fb.update(status="Goto line: {}_".format(self._pbuf), status_kind="info", hints="ENTER:Go ESC:Cancel")
        elif self.mode == "confirm":
            self.fb.update(status="Save changes?", status_kind="warn", hints="Y:Save N:Discard ESC:Cancel")
        else:
            self.fb.update(status=self.status, status_kind=self.status_kind,
                           hints="^S:Save ^X:Exit ^F:Find ^G:Goto ^K:Cut ^U:Paste")
        ui.render(force=force)

    def _find(self, term):
        if not term:
            return
        self.last_find = term
        t = term.lower()
        n = len(self.lines)
        for step in range(n + 1):
            i = (self.cy + step) % n
            k = self.lines[i].lower().find(t, self.cx + 1 if step == 0 else 0)
            if k >= 0:
                self.cy, self.cx = i, k
                self._set("Found at L{}".format(i + 1), "ok")
                return
        self._set("Not found: " + term[:20], "warn")

    def _request_exit(self):
        if self.modified and not self.readonly:
            self.mode = "confirm"
        else:
            self._result = "closed " + _basename(self.path)

    def run(self):
        try:
            self.load()
        except Exception as e:
            return "edit: {}".format(e)
        self._mount()
        self.board.clear_input()
        self.refresh(force=True)
        idle = 0
        while self._result is None:
            k = self.board.poll_key()
            if k is None:
                idle += 1
                if idle >= 100:
                    idle = 0
                    gc.collect()
                _sleep_ms(30)
                continue
            idle = 0
            mods = self.board.get_modifiers()
            ctrl = bool(mods & MOD_CTRL)
            shift = bool(mods & MOD_SHIFT)
            if (ctrl and len(k) == 1 and k.upper() == "P") or getattr(self.board, "pending_screenshot", None):
                from ui.menu import show_screenshot_toast
                _, smsg = show_screenshot_toast(self.board, self.ui, self.fb)
                if smsg:
                    self._set(smsg, "ok")
                self.refresh(force=True)
                continue

            if self.mode in ("find", "goto"):
                if k == "ESC" or (ctrl and k.upper() == "C"):
                    self.mode = "edit"; self._set("Cancelled", "info")
                elif k == "ENTER":
                    txt = self._pbuf or (self.last_find if self.mode == "find" else "")
                    m = self.mode; self.mode = "edit"
                    if m == "find":
                        self._find(txt)
                    else:
                        try:
                            self.cy = max(0, min(len(self.lines) - 1, int(txt) - 1)); self.cx = 0
                        except ValueError:
                            self._set("Not a number", "err")
                elif k == "BACKSPACE":
                    self._pbuf = self._pbuf[:-1]
                elif k == "SPACE":
                    self._pbuf += " "
                elif len(k) == 1 and " " <= k <= "~" and not ctrl:
                    self._pbuf += k
            elif self.mode == "confirm":
                ku = k.upper()
                if ku == "Y":
                    if self.save():
                        self._result = "saved " + _basename(self.path)
                    else:
                        self.mode = "edit"
                elif ku == "N":
                    self._result = "discarded " + _basename(self.path)
                else:
                    self.mode = "edit"; self._set("Cancelled", "info")
            else:
                page = max(1, self.ui.backend.term_metrics(self.tv)[4] - 1)
                ro = self.readonly
                if ctrl and len(k) == 1:
                    c = k.upper()
                    if c == "S":
                        self.save()
                    elif c == "X":
                        self._request_exit()
                    elif c == "F":
                        self.mode = "find"; self._pbuf = ""
                    elif c == "G":
                        self.mode = "goto"; self._pbuf = ""
                    elif c == "K" and not ro:
                        self.clip = self.lines[self.cy]
                        if len(self.lines) > 1:
                            del self.lines[self.cy]
                            self.cy = min(self.cy, len(self.lines) - 1)
                        else:
                            self.lines[0] = ""
                        self.cx = 0; self.modified = True; self._set("Cut line", "info")
                    elif c == "U" and not ro and self.clip is not None:
                        self.lines.insert(self.cy, self.clip); self.cy += 1; self.modified = True
                    elif c == "A":
                        self.cx = 0
                    elif c == "E":
                        self.cx = len(self.lines[self.cy])
                elif k == "ESC":
                    self._request_exit()
                elif k == "UP":
                    self.cy = max(0, self.cy - (page if shift else 1))
                    self.cx = min(self.cx, len(self.lines[self.cy]))
                elif k == "DOWN":
                    self.cy = min(len(self.lines) - 1, self.cy + (page if shift else 1))
                    self.cx = min(self.cx, len(self.lines[self.cy]))
                elif k == "LEFT":
                    if shift:
                        self.cx = 0
                    elif self.cx > 0:
                        self.cx -= 1
                    elif self.cy > 0:
                        self.cy -= 1; self.cx = len(self.lines[self.cy])
                elif k == "RIGHT":
                    if shift:
                        self.cx = len(self.lines[self.cy])
                    elif self.cx < len(self.lines[self.cy]):
                        self.cx += 1
                    elif self.cy + 1 < len(self.lines):
                        self.cy += 1; self.cx = 0
                elif ro:
                    self._set("Read-only (>16KB)", "warn")
                elif k == "ENTER":
                    ln = self.lines[self.cy]
                    self.lines[self.cy] = ln[:self.cx]
                    self.lines.insert(self.cy + 1, ln[self.cx:])
                    self.cy += 1; self.cx = 0; self.modified = True
                elif k == "BACKSPACE":
                    if self.cx > 0:
                        ln = self.lines[self.cy]
                        self.lines[self.cy] = ln[:self.cx - 1] + ln[self.cx:]
                        self.cx -= 1; self.modified = True
                    elif self.cy > 0:
                        prev = self.lines[self.cy - 1]
                        self.cx = len(prev)
                        self.lines[self.cy - 1] = prev + self.lines[self.cy]
                        del self.lines[self.cy]; self.cy -= 1; self.modified = True
                elif k == "TAB":
                    ln = self.lines[self.cy]
                    self.lines[self.cy] = ln[:self.cx] + (" " * TAB_WIDTH) + ln[self.cx:]
                    self.cx += TAB_WIDTH; self.modified = True
                elif k == "SPACE":
                    ln = self.lines[self.cy]
                    self.lines[self.cy] = ln[:self.cx] + " " + ln[self.cx:]
                    self.cx += 1; self.modified = True
                elif len(k) == 1 and " " <= k <= "~":
                    ln = self.lines[self.cy]
                    self.lines[self.cy] = ln[:self.cx] + k + ln[self.cx:]
                    self.cx += 1; self.modified = True

            if self._result is None:
                self.refresh()

        res = self._result
        self.lines = None
        self.ui.clear_widgets()
        gc.collect()
        return res


def main(ctx):
    if ctx.board is None or ctx.ui is None:
        return {"error": "no board/ui"}
    path = "/sd/pinhos/config.json"
    if isinstance(ctx.args, dict) and ctx.args.get("path"):
        path = str(ctx.args["path"])
    ed = Editor(ctx.board, ctx.ui, path, logger=ctx.logger)
    return {"result": ed.run(), "path": path}

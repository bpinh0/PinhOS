# PinhOS Phase 3 — File Commander (tools/files.py)
# Keyboard-driven file browser across /sd and /, with copy/move/rename/delete/mkdir,
# 1 KB streaming text/JSON viewer, 8-byte hex inspector, and on-device editor launch.
# Zero full-screen framebuffers; zero hardcoded GPIO pins.

APP_META = {
    "id": "file_commander",
    "name": "File Commander",
    "version": "1.0.0",
    "category": "Field Tools",
    "description": "Browse /sd & flash, copy/move/rename/delete, 1KB text viewer & hex inspector",
    "entry": "main",
    "min_sram": 40960,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}

import gc
import os
import time

CHUNK = 1024
PROTECTED = ("/", "/sd", "/flash", "/sd/pinhos", "/boot.py", "/main.py")


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _hsize(n):
    if n < 1024:
        return "{}B".format(n)
    if n < 1048576:
        return "{:.1f}K".format(n / 1024.0) if n < 10240 else "{}K".format(n // 1024)
    return "{:.1f}M".format(n / 1048576.0)


def _join(base, name):
    return (base.rstrip("/") + "/" + name) if base != "/" else ("/" + name)


def _parent(path):
    p = path.rstrip("/")
    if not p or p == "/":
        return "/"
    idx = p.rfind("/")
    return p[:idx] if idx > 0 else "/"


def list_dir_entries(path):
    """Return sorted list of entry dicts: {name, path, is_dir, size}."""
    entries = []
    if path != "/":
        entries.append({"name": "..", "path": _parent(path), "is_dir": True, "size": 0, "up": True})
    dirs, files = [], []
    try:
        for e in os.ilistdir(path):
            nm = e[0]
            full = _join(path, nm)
            isd = (e[1] == 0x4000)
            sz = 0
            if not isd:
                try:
                    sz = e[3] if len(e) > 3 else os.stat(full)[6]
                except Exception:
                    sz = 0
            rec = {"name": nm, "path": full, "is_dir": isd, "size": sz}
            (dirs if isd else files).append(rec)
    except OSError:
        pass
    dirs.sort(key=lambda r: r["name"].lower())
    files.sort(key=lambda r: r["name"].lower())
    entries.extend(dirs)
    entries.extend(files)
    return entries


MAX_LINE_COLS = 96
MAX_CARRY = 128


def _sanitize_line(raw, max_cols=MAX_LINE_COLS):
    """Sanitize raw bytes in-place into printable ASCII without per-char list allocs."""
    if not raw:
        return ""
    if len(raw) > max_cols:
        raw = raw[:max_cols]
    buf = bytearray(raw)
    for i in range(len(buf)):
        c = buf[i]
        if c < 32 or c >= 127:
            buf[i] = 46  # '.'
    return buf.decode("ascii")


def is_binary_file(path):
    """Return True if first 256 bytes contain a NUL byte (0x00)."""
    try:
        f = open(path, "rb")
        try:
            head = f.read(256)
        finally:
            f.close()
        return b"\x00" in head
    except Exception:
        return False


def read_text_preview(path, offset=0, max_bytes=2048):
    """Stream up to max_bytes in <= 1 KB chunks into display-safe lines (bounded SRAM)."""
    lines = []
    carry = b""
    done = 0
    f = open(path, "rb")
    try:
        if offset > 0:
            f.seek(offset)
        while done < max_bytes:
            ch = f.read(min(CHUNK, max_bytes - done))
            if not ch:
                break
            done += len(ch)
            data = carry + ch
            carry = b""
            pos = 0
            n = len(data)
            while pos < n:
                nl = data.find(b"\n", pos)
                if nl < 0:
                    rem = data[pos:]
                    while len(rem) >= MAX_CARRY:
                        lines.append(_sanitize_line(rem[:MAX_LINE_COLS]))
                        rem = rem[MAX_LINE_COLS:]
                    carry = rem
                    break
                seg = data[pos:nl]
                if seg[-1:] == b"\r":
                    seg = seg[:-1]
                lines.append(_sanitize_line(seg))
                pos = nl + 1
        if carry:
            if carry[-1:] == b"\r":
                carry = carry[:-1]
            lines.append(_sanitize_line(carry))
    finally:
        f.close()
    return lines, done


def read_hex_preview(path, offset=0, max_bytes=256):
    """Format 8 bytes per row (<= 50 chars) using <= 1 KB streaming reads."""
    rows = []
    f = open(path, "rb")
    try:
        if offset > 0:
            f.seek(offset)
        rem = max_bytes
        off = offset
        while rem > 0:
            ch = f.read(min(CHUNK, rem))
            if not ch:
                break
            for i in range(0, len(ch), 8):
                blk = ch[i:i + 8]
                hx = " ".join(["{:02x}".format(c) for c in blk])
                asc = "".join([chr(c) if 32 <= c < 127 else "." for c in blk])
                rows.append("{:06x}: {:<23} |{}|".format(off + i, hx, asc))
            off += len(ch)
            rem -= len(ch)
    finally:
        f.close()
    return rows


def copy_file_stream(src, dst):
    """Copy a file in 1 KB chunks to protect RP2350 SRAM."""
    fi = open(src, "rb")
    try:
        fo = open(dst, "wb")
        try:
            while True:
                b = fi.read(CHUNK)
                if not b:
                    break
                fo.write(b)
        finally:
            fo.close()
    finally:
        fi.close()


def _prompt_line(board, ui, fb, label, initial=""):
    buf = str(initial)
    board.clear_input()
    while True:
        fb.update(status="{}: {}_".format(label, buf[-36:]), status_kind="info", hints="ENTER:OK  ESC:Cancel")
        ui.render(force=False)
        k = board.poll_key()
        if k is None:
            _sleep_ms(30)
            continue
        if getattr(board, "pending_screenshot", None):
            from ui.widgets import show_screenshot_toast
            show_screenshot_toast(board, ui, fb)
            continue
        if k == "ESC":
            return None
        if k == "ENTER":
            return buf.strip()
        if k == "BACKSPACE":
            buf = buf[:-1]
        elif k == "SPACE":
            buf += " "
        elif len(k) == 1 and " " <= k <= "~":
            buf += k


def _open_viewer(board, ui, path, hex_mode=False):
    from ui.widgets import StatusBar, TextView, FooterBar
    sb = StatusBar(0, 0, 320, 20, title="", mode_label=ui.mode_badge)
    tv = TextView(4, 23, 312, 250, title="", lines=[])
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info",
                   hints="UP/DN:Scr H:Hex/Txt N/P:Page ESC:Back")
    offset = 0
    size = 0
    try:
        size = os.stat(path)[6]
    except OSError:
        pass

    if not hex_mode and is_binary_file(path):
        hex_mode = True

    def load_page():
        gc.collect()
        if hex_mode:
            lines = read_hex_preview(path, offset=offset, max_bytes=256)
            tv.title = "HEX @0x{:X} ({})".format(offset, _hsize(size))
        else:
            lines, _n = read_text_preview(path, offset=offset, max_bytes=2048)
            tv.title = "TXT @{} ({})".format(_hsize(offset), _hsize(size))
        tv.set_lines(lines or ["(empty file)"], reset_scroll=True)
        sb.update(title=path[-28:], mode_label=ui.mode_badge, right_text="HEX" if hex_mode else "TXT")
        fb.update(status="{} ({} B)".format(path[-32:], size), status_kind="ok")

    ui.clear_widgets()
    ui.add_widget(sb); ui.add_widget(tv); ui.add_widget(fb)
    ui.set_focus(tv)
    load_page()
    ui.render(force=True)
    board.clear_input()
    while True:
        k = board.poll_key()
        if k is None:
            _sleep_ms(30)
            continue
        ku = k.upper()
        if getattr(board, "pending_screenshot", None):
            from ui.widgets import show_screenshot_toast
            show_screenshot_toast(board, ui, fb)
            continue
        if ku in ("ESC", "Q", "BACKSPACE"):
            break
        elif ku == "UP":
            if tv.scroll(-2):
                ui.render(force=False)
        elif ku == "DOWN":
            if tv.scroll(2):
                ui.render(force=False)
        elif ku == "H":
            hex_mode = not hex_mode
            load_page(); ui.render(force=True)
        elif ku == "N":
            step = 256 if hex_mode else 2048
            if offset + step < size:
                offset += step
                load_page(); ui.render(force=True)
        elif ku == "P":
            step = 256 if hex_mode else 2048
            offset = max(0, offset - step)
            load_page(); ui.render(force=True)
    gc.collect()


def main(ctx):
    board, ui = ctx.board, ctx.ui
    if board is None or ui is None:
        return {"error": "no board/ui"}

    from ui.widgets import StatusBar, ListMenu, FooterBar
    cwd = "/sd/pinhos"
    try:
        os.listdir(cwd)
    except OSError:
        cwd = "/"

    sb = StatusBar(0, 0, 320, 20, title="Files", mode_label=ui.mode_badge)
    menu = ListMenu(4, 23, 312, 250, title=cwd, items=[])
    hints = "ENT:Open H:Hex E:Edit C:Cp R:Ren D:Del N:Dir ESC"
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=hints)

    entries = []
    clip = None  # ("cp"|"mv", src_path, src_name)
    status_msg = "Browse /sd & flash (1KB streaming)"
    status_kind = "info"

    def mount():
        ui.clear_widgets()
        ui.add_widget(sb); ui.add_widget(menu); ui.add_widget(fb)
        ui.set_focus(menu)

    def reload_dir(sel=0):
        nonlocal entries
        entries = list_dir_entries(cwd)
        items = []
        for e in entries:
            lbl = "[..]" if e.get("up") else (e["name"] + "/" if e["is_dir"] else e["name"])
            bdg = "DIR" if e["is_dir"] else _hsize(e["size"])
            items.append({"label": lbl, "badge": bdg, "entry": e})
        menu.title = cwd[-32:]
        menu.set_items(items, selected=sel)
        sb.update(title="Files: " + cwd[-22:], mode_label=ui.mode_badge, right_text="{} itm".format(len(entries)))
        fb.update(status=status_msg, status_kind=status_kind, hints=hints)

    mount()
    reload_dir(0)
    ui.render(force=True)
    board.clear_input()

    try:
        while True:
            k = board.poll_key()
            if k is None:
                _sleep_ms(30)
                continue
            ku = k.upper()
            try:
                from boards.base import MOD_CTRL
                ctrl = bool(board.get_modifiers() & MOD_CTRL)
            except Exception:
                ctrl = False
            if (ctrl and ku == "P") or getattr(board, "pending_screenshot", None):
                from ui.widgets import show_screenshot_toast
                _, smsg = show_screenshot_toast(board, ui, fb)
                if smsg:
                    status_msg, status_kind = smsg, "ok"
                    fb.update(status=status_msg, status_kind=status_kind)
                    ui.render(force=True)
                continue
            item = menu.get_selected_item()
            ent = item.get("entry") if isinstance(item, dict) else None

            if ku in ("ESC", "Q"):
                break
            elif ku in ("UP", "DOWN"):
                if ui.handle_key(ku, allow_hotkeys=False):
                    ui.render(force=False)
            elif ku in ("BACKSPACE", "LEFT"):
                if cwd != "/":
                    cwd = _parent(cwd)
                    status_msg = "Up -> " + cwd; status_kind = "info"
                    reload_dir(0); ui.render(force=True)
            elif ku in ("ENTER", "RIGHT"):
                if ent is not None:
                    if ent["is_dir"]:
                        cwd = ent["path"]
                        status_msg = "Dir: " + cwd; status_kind = "info"
                        reload_dir(0); ui.render(force=True)
                    else:
                        _open_viewer(board, ui, ent["path"], hex_mode=False)
                        mount(); reload_dir(menu.selected); ui.render(force=True)
            elif ku == "H" and ent and not ent["is_dir"]:
                _open_viewer(board, ui, ent["path"], hex_mode=True)
                mount(); reload_dir(menu.selected); ui.render(force=True)
            elif ku == "E" and ent and not ent["is_dir"]:
                from tools.editor import Editor
                ed = Editor(board, ui, ent["path"], logger=ctx.logger)
                status_msg = ed.run(); status_kind = "ok"
                ed = None
                mount(); reload_dir(menu.selected); ui.render(force=True)
            elif ku == "C" and ent and not ent["is_dir"]:
                clip = ("cp", ent["path"], ent["name"])
                status_msg = "Copied {} (V to paste)".format(ent["name"]); status_kind = "ok"
                fb.update(status=status_msg, status_kind=status_kind); ui.render(force=False)
            elif ku == "X" and ent and not ent["is_dir"]:
                clip = ("mv", ent["path"], ent["name"])
                status_msg = "Cut {} (V to move here)".format(ent["name"]); status_kind = "warn"
                fb.update(status=status_msg, status_kind=status_kind); ui.render(force=False)
            elif ku == "V" and clip is not None:
                op, src, nm = clip
                dst = _join(cwd, nm)
                try:
                    if op == "cp":
                        copy_file_stream(src, dst)
                        status_msg = "Pasted " + nm
                    else:
                        try:
                            os.rename(src, dst)
                        except OSError:
                            copy_file_stream(src, dst); os.remove(src)
                        clip = None
                        status_msg = "Moved " + nm
                    status_kind = "ok"
                except Exception as e:
                    status_msg = "Err: " + str(e); status_kind = "err"
                reload_dir(menu.selected); ui.render(force=True)
            elif ku == "R" and ent and not ent.get("up"):
                if ent["path"].rstrip("/") in PROTECTED:
                    status_msg = "Protected path!"; status_kind = "err"
                else:
                    nn = _prompt_line(board, ui, fb, "Rename", ent["name"])
                    if nn and nn != ent["name"]:
                        try:
                            os.rename(ent["path"], _join(cwd, nn))
                            status_msg = "Renamed -> " + nn; status_kind = "ok"
                        except Exception as e:
                            status_msg = "Err: " + str(e); status_kind = "err"
                reload_dir(menu.selected); ui.render(force=True)
            elif ku == "N":
                dn = _prompt_line(board, ui, fb, "New dir", "")
                if dn:
                    try:
                        os.mkdir(_join(cwd, dn))
                        status_msg = "Created " + dn + "/"; status_kind = "ok"
                    except Exception as e:
                        status_msg = "Err: " + str(e); status_kind = "err"
                reload_dir(menu.selected); ui.render(force=True)
            elif ku == "D" and ent and not ent.get("up"):
                p = ent["path"].rstrip("/") or "/"
                if p in PROTECTED:
                    status_msg = "Refused: protected path"; status_kind = "err"
                    fb.update(status=status_msg, status_kind=status_kind); ui.render(force=False)
                else:
                    ans = _prompt_line(board, ui, fb, "Del {} (y/n)".format(ent["name"][:14]), "")
                    if ans and ans.lower() == "y":
                        try:
                            os.rmdir(p) if ent["is_dir"] else os.remove(p)
                            status_msg = "Deleted " + ent["name"]; status_kind = "warn"
                        except Exception as e:
                            status_msg = "Del err: " + str(e); status_kind = "err"
                    reload_dir(max(0, menu.selected - 1)); ui.render(force=True)
            elif ku in ("M", "TAB"):
                ui.toggle_mode(persist=True)
                reload_dir(menu.selected); ui.render(force=True)
            elif ku == "T":
                ui.cycle_theme(step=1, persist=True)
                reload_dir(menu.selected); ui.render(force=True)
        return {"cwd": cwd}
    finally:
        ui.clear_widgets()
        gc.collect()

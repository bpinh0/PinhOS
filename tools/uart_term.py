# PinhOS Phase 3 — Hardware UART Serial Console (tools/uart_term.py)
# Routes strictly through board HAL (board.open_aux_uart / close_aux_uart -> UART1)
# so UART0 COM4 dupterm is never disturbed and zero GPIO pins are hardcoded here.
# Supports baud presets (9600..921600), 8N1 framing, ASCII/Hex toggle, SD logging & macros.

APP_META = {
    "id": "uart_term",
    "name": "UART Console",
    "version": "1.0.0",
    "category": "Field Tools",
    "description": "HAL-routed UART1 terminal with baud presets, ASCII/Hex, SD log & macros",
    "entry": "main",
    "min_sram": 40960,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}

import gc
import time

try:
    from boards.base import MOD_CTRL
except Exception:
    MOD_CTRL = 2

BAUD_PRESETS = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)
DEFAULT_MACROS = {
    "F1": "AT\r\n",
    "F4": "help\r\n",
    "F5": "uname -a\r\n",
    "F6": "status\r\n",
}
LOG_PATH = "/sd/pinhos/logs/uart_session.log"


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def format_rx_chunk(data, hex_mode=False):
    """Format raw RX bytes into 53-col display lines."""
    if not data:
        return []
    if hex_mode:
        rows = []
        for i in range(0, len(data), 12):
            blk = data[i:i + 12]
            hx = " ".join(["{:02x}".format(b) for b in blk])
            asc = "".join([chr(b) if 32 <= b < 127 else "." for b in blk])
            rows.append("{} |{}|".format(hx, asc))
        return rows
    txt = "".join([chr(b) if (32 <= b < 127 or b == 10) else "" for b in data])
    out = []
    for ln in txt.split("\n"):
        if ln:
            for i in range(0, len(ln), 52):
                out.append(ln[i:i + 52])
    return out


def main(ctx):
    board, ui = ctx.board, ctx.ui
    if board is None or ui is None:
        return {"error": "no board/ui"}

    from ui.widgets import StatusBar, TermView, FooterBar, layout_term_screen

    baud_idx = 4  # 115200
    hex_mode = False
    log_file = None
    uart = None
    rx_bytes = 0
    tx_bytes = 0
    ring = []
    max_ring = 120
    tx_buf = ""

    sb = StatusBar(0, 0, 320, 20, title="UART1 8N1", mode_label=ui.mode_badge)
    tv = TermView()
    hints = "F2:Hex F3:Log ^B:Baud F1/F4:Macro ESC:Exit"
    fb = FooterBar(0, 276, 320, 44, status="", status_kind="info", hints=hints)

    def push_line(text, tag=" "):
        if len(ring) >= max_ring:
            ring.pop(0)
        ring.append(tag + str(text)[:52])

    def open_port():
        nonlocal uart
        baud = BAUD_PRESETS[baud_idx]
        uart = board.open_aux_uart(baud=baud, bits=8, parity=None, stop=1) if hasattr(board, "open_aux_uart") else None
        if uart is not None:
            push_line("UART1 opened @ {} 8N1".format(baud), "o")
        else:
            push_line("UART1 unavailable (loopback preview @ {})".format(baud), "w")

    def send_data(raw_str):
        nonlocal tx_bytes
        b = raw_str.encode("utf-8")
        tx_bytes += len(b)
        if uart is not None:
            try:
                uart.write(b)
            except Exception as e:
                push_line("TX err: {}".format(e), "e")
        else:
            for ln in format_rx_chunk(b, hex_mode=hex_mode):
                push_line("[LB] " + ln, "m")
        if log_file is not None:
            try:
                log_file.write(">> " + raw_str.replace("\r", "") + "\n")
            except Exception:
                pass

    def refresh(force=False):
        geom = ui.backend.term_metrics(tv)
        nrows = geom[4]
        vis = ring[-(nrows - 1):] if nrows > 1 else []
        rows = list(vis)
        prompt = "TX> " + tx_buf[-47:]
        rows.append("p" + prompt)
        tv.lead_cols = 4
        tv.set_rows(rows, (len(rows) - 1, min(geom[3] - 1, len(prompt))))
        baud = BAUD_PRESETS[baud_idx]
        sb.update(
            title="UART1 {} 8N1".format(baud),
            mode_label=ui.mode_badge,
            right_text="{}{}".format("HEX" if hex_mode else "ASC", " LOG" if log_file else ""),
        )
        fb.update(
            status="RX:{}B TX:{}B | {}".format(rx_bytes, tx_bytes, "HW" if uart else "SIM"),
            status_kind="ok" if uart else "warn",
            hints=hints,
        )
        ui.render(force=force)

    ui.clear_widgets()
    ui.add_widget(sb); ui.add_widget(tv); ui.add_widget(fb)
    ui.set_focus(tv)
    layout_term_screen(ui.mode, sb, tv, fb)
    push_line("PinhOS UART1 Console (UART0 COM4 untouched)", "c")
    push_line("Macros: F1=AT  F4=help  F5=uname  F6=status", "m")
    open_port()
    refresh(force=True)
    board.clear_input()

    try:
        idle = 0
        while True:
            dirty = False
            if uart is not None:
                try:
                    avail = uart.any()
                    if avail:
                        raw = uart.read(min(256, avail))
                        if raw:
                            rx_bytes += len(raw)
                            for ln in format_rx_chunk(raw, hex_mode=hex_mode):
                                push_line(ln, " ")
                            if log_file is not None:
                                log_file.write("".join([chr(c) if 32 <= c < 127 or c == 10 else "." for c in raw]))
                            dirty = True
                except Exception:
                    pass

            k = board.poll_key()
            if k is not None:
                idle = 0
                mods = board.get_modifiers()
                ctrl = bool(mods & MOD_CTRL)
                if (ctrl and len(k) == 1 and k.upper() == "P") or getattr(board, "pending_screenshot", None):
                    from ui.widgets import show_screenshot_toast
                    show_screenshot_toast(board, ui, fb)
                    refresh(force=True)
                    continue
                if k == "ESC":
                    break
                elif ctrl and k.upper() == "B":
                    baud_idx = (baud_idx + 1) % len(BAUD_PRESETS)
                    open_port(); dirty = True
                elif ctrl and k.upper() == "L":
                    ring.clear(); dirty = True
                elif k == "F2":
                    hex_mode = not hex_mode
                    push_line("Display: " + ("HEX" if hex_mode else "ASCII"), "c")
                    dirty = True
                elif k == "F3":
                    if log_file is None:
                        try:
                            log_file = open(LOG_PATH, "a")
                            push_line("Logging -> " + LOG_PATH, "o")
                        except Exception as e:
                            push_line("Log err: {}".format(e), "e")
                    else:
                        try:
                            log_file.close()
                        except Exception:
                            pass
                        log_file = None
                        push_line("SD logging stopped", "w")
                    dirty = True
                elif k in DEFAULT_MACROS:
                    m = DEFAULT_MACROS[k]
                    push_line("MACRO {}: {}".format(k, m.strip()), "c")
                    send_data(m); dirty = True
                elif k == "ENTER":
                    if tx_buf:
                        push_line("TX> " + tx_buf, "c")
                        send_data(tx_buf + "\r\n")
                        tx_buf = ""
                    else:
                        send_data("\r\n")
                    dirty = True
                elif k == "BACKSPACE":
                    tx_buf = tx_buf[:-1]; dirty = True
                elif k == "SPACE":
                    tx_buf += " "; dirty = True
                elif len(k) == 1 and " " <= k <= "~" and not ctrl:
                    tx_buf += k; dirty = True
            else:
                idle += 1
                if idle >= 100:
                    idle = 0
                    gc.collect()

            if dirty:
                refresh(force=False)
            else:
                _sleep_ms(20)
        return {"rx_bytes": rx_bytes, "tx_bytes": tx_bytes, "baud": BAUD_PRESETS[baud_idx]}
    finally:
        if log_file is not None:
            try:
                log_file.close()
            except Exception:
                pass
        if hasattr(board, "close_aux_uart"):
            board.close_aux_uart()
        ui.clear_widgets()
        gc.collect()

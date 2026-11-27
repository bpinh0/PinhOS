# PinhOS — On-Demand License & Legal Notices Viewer (ui/_legal_view.py)
# Streams /sd/pinhos/NOTICE and /sd/pinhos/LICENSE in <= 1 KB chunks into a
# scrollable Dual-UI TextView while feeding __pinhos_wdt__. Purged cleanly on exit (#58).

import gc
import time
from core.config import PINHOS_ROOT


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


def _append_wrapped(dst, txt, tok, cols=49):
    if not txt:
        dst.append(("", "text"))
        return
    for i in range(0, len(txt), cols):
        dst.append((txt[i:i + cols], tok))


def _stream_into(dst, path, cols=49, max_bytes=4096, max_lines=115, heading_tok="info"):
    """Stream text file line-by-line (zero multi-KB intermediate buffer) into wrapped lines."""
    read_b = 0
    added = 0
    try:
        with open(path, "r") as f:
            for raw in f:
                read_b += len(raw)
                s = raw.strip()
                tok = heading_tok if s.startswith("#") else "text"
                _append_wrapped(dst, s, tok, cols)
                added += 1
                if read_b >= max_bytes or len(dst) >= max_lines:
                    break
    except OSError:
        return 0
    except Exception:
        return added
    return added


def build_legal_lines(root=PINHOS_ROOT, cols=49):
    """Build wrapped (text, color_token) lines for the License & Legal Notices TextView."""
    r = root.rstrip("/")
    wrapped = []
    for txt, tok in (
        ("=== PINHOS LICENSE & LEGAL NOTICES ===", "info"),
        ("", "text"),
        ("[REQUIRED NOTICE]", "warn"),
    ):
        _append_wrapped(wrapped, txt, tok, cols)

    if _stream_into(wrapped, r + "/NOTICE", cols=cols, max_bytes=1024, heading_tok="text") == 0:
        _append_wrapped(
            wrapped,
            "Required Notice: Copyright (c) 2026 Bruno Pinho (bpinh0) (https://github.com/bpinh0/PinhOS)",
            "text",
            cols,
        )

    for txt, tok in (
        ("", "text"),
        ("[LICENSE SUMMARY]", "info"),
        ("PolyForm Noncommercial License 1.0.0", "ok"),
        ("Personal, hobbyist, educational & noncommercial", "text"),
        ("use/modification/sharing permitted.", "text"),
        ("Commercial use is NOT permitted without consent.", "warn"),
        ("", "text"),
        ("[THIRD-PARTY NOTICES]", "info"),
        ("MicroPython (RP2350 UF2): MIT License", "text"),
        ("ClockworkPi PicoCalc HAL & Fonts: OSS/MIT", "text"),
        ("", "text"),
        ("=== FULL LICENSE TEXT ===", "info"),
    ):
        _append_wrapped(wrapped, txt, tok, cols)

    if _stream_into(wrapped, r + "/LICENSE", cols=cols, max_bytes=6144, heading_tok="info") == 0:
        _append_wrapped(wrapped, "(See https://polyformproject.org/licenses/noncommercial/1.0.0)", "text", cols)
    return wrapped


def open_legal_viewer(board, ui, root=PINHOS_ROOT):
    """Display scrollable License & Legal Notices viewer while keeping WDT fed (#58)."""
    from ui.widgets import StatusBar, TextView, FooterBar
    sb = StatusBar(0, 0, 320, 20, title="License & Legal Notices", mode_label=ui.mode_badge)
    lines = build_legal_lines(root=root, cols=49)
    tv = TextView(4, 23, 312, 250, title="POLYFORM NC 1.0 ({} ln)".format(len(lines)), lines=lines)
    fb = FooterBar(
        0, 276, 320, 44,
        status="PolyForm Noncommercial 1.0.0",
        status_kind="info",
        hints="UP/DN:Scroll  L/R:Page  ESC/Q:Back",
    )
    ui.clear_widgets(); ui.add_widget(sb); ui.add_widget(tv); ui.add_widget(fb); ui.set_focus(tv)
    ui.render(force=True); board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    try:
        while True:
            try:
                import sys as _sys
                _w = _sys.modules.get("__pinhos_wdt__")
                if _w is not None:
                    _w.feed()
            except Exception:
                pass
            k = poll_fn() if poll_fn else None
            if k:
                ku = str(k).upper()
                if ku in ("ESC", "Q", "BACK", "BACKSPACE"):
                    board.beep(900, 10); break
                elif ku == "UP" and tv.scroll(-2):
                    ui.render(force=False)
                elif ku == "DOWN" and tv.scroll(2):
                    ui.render(force=False)
                elif ku == "LEFT" and tv.scroll(-10):
                    ui.render(force=False)
                elif ku == "RIGHT" and tv.scroll(10):
                    ui.render(force=False)
            _sleep_ms(30)
    except KeyboardInterrupt:
        pass
    gc.collect()

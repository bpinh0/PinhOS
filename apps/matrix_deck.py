# PinhOS Phase 2 Sandboxed Applet: Matrix Cyberdeck Rain (apps/matrix_deck.py)

APP_META = {
    "id": "matrix_deck",
    "name": "Matrix Cyber Rain",
    "version": "1.1.0",
    "category": "Media",
    "description": "Theme-aware falling digital rain screensaver with live SRAM HUD",
    "entry": "main",
    "min_sram": 24576,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}


def _tok(theme, name, fallback):
    if theme is not None and hasattr(theme, "color"):
        return theme.color(name)
    return fallback


def main(ctx):
    import gc
    import time
    import random

    board = ctx.board
    if board is None:
        return {"frames": 0}

    theme = getattr(ctx, "theme", None)
    c_bg = _tok(theme, "bg", 0)
    c_surf = _tok(theme, "surface", 1)
    c_ok = _tok(theme, "ok", 10)
    c_acc = _tok(theme, "accent", 3)
    c_txt = _tok(theme, "text", 15)
    c_muted = _tok(theme, "text_muted", 6)

    cols = [random.randint(-20, 0) for _ in range(40)]
    max_frames = int(ctx.args.get("max_frames", 120)) if isinstance(ctx.args, dict) else 120
    frames = 0

    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while frames < max_frames:
        if poll_fn and poll_fn() is not None:
            break
        board.fill(c_bg)
        for cx in range(40):
            ry = cols[cx]
            if 0 <= ry < 36:
                ch = chr(random.randint(33, 90))
                board.text(ch, cx * 8, ry * 8, c_ok if (cx & 1) == 0 else c_acc)
                if ry > 1:
                    board.text(chr(random.randint(33, 90)), cx * 8, (ry - 1) * 8, c_muted)
            cols[cx] = (ry + 1) if ry < 38 else random.randint(-15, 0)
        board.fill_rect(36, 128, 248, 56, c_surf)
        board.rect(36, 128, 248, 56, c_acc)
        board.text("[ PinhOS // MATRIX RAIN ]", 56, 140, c_acc)
        free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        board.text("SRAM FREE: {}KB | ANY KEY".format(free_kb), 56, 162, c_txt)
        board.show()
        frames += 1
        if (frames & 15) == 0:
            gc.collect()
        if hasattr(time, "sleep_ms"):
            time.sleep_ms(35)
        else:
            time.sleep(0.035)

    return {"frames": frames}

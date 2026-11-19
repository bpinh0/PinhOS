# PinhOS Sandboxed Applet: Matrix Cyberdeck Rain (apps/matrix_deck.py)

APP_META = {
    "id": "matrix_deck",
    "name": "Matrix Cyber Rain",
    "version": "1.0.0",
    "category": "Media",
    "description": "Falling digital rain screensaver with live SRAM HUD",
    "entry": "main",
    "min_sram": 24576,
    "ui_modes": ["native"],
    "native_libs": []
}


def main(ctx):
    import gc
    import time
    import random

    board = ctx.board
    if board is None:
        return {"frames": 0}

    cols = [random.randint(-20, 0) for _ in range(40)]
    max_frames = int(ctx.args.get("max_frames", 120)) if isinstance(ctx.args, dict) else 120
    frames = 0

    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)
    while frames < max_frames:
        if poll_fn and poll_fn() is not None:
            break
        board.fill(0)
        for cx in range(40):
            ry = cols[cx]
            if 0 <= ry < 36:
                ch = chr(random.randint(33, 90))
                board.text(ch, cx * 8, ry * 8, 10)
            cols[cx] = (ry + 1) if ry < 38 else random.randint(-15, 0)
        board.fill_rect(40, 130, 240, 52, 0)
        board.rect(40, 130, 240, 52, 10)
        board.text("[ PinhOS // MATRIX RAIN ]", 56, 142, 10)
        free_kb = (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else 256
        board.text("SRAM FREE: {}KB | ANY KEY".format(free_kb), 56, 162, 15)
        board.show()
        frames += 1
        if hasattr(time, "sleep_ms"):
            time.sleep_ms(35)
        else:
            time.sleep(0.035)

    return {"frames": frames}

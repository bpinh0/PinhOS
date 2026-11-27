# PinhOS Official App Starter Template (docs/templates/app_template.py)
# Copy this file to /sd/pinhos/apps/<your_app_id>.py and validate with:
#   .\picocalc.ps1 lint apps/<your_app_id>.py
#
# Rules enforced by SandboxRunner BEFORE your code compiles or executes:
# 1. APP_META must be a static dict literal near the top of the file (first 1.5 KB).
# 2. id: 2-24 chars [a-z0-9_], starting with a-z; min_sram >= 16384; ui_modes subset of gui/tui/native.
# 3. Never touch raw GPIO (machine.Pin), machine.WDT, machine.reset(), os.dupterm(),
#    stopRefresh()/recoverRefresh(), or board.poll_input(). Always use ctx.board.poll_key().

import gc
import time

APP_META = {
    "id": "my_app",
    "name": "My PinhOS App",
    "version": "1.0.0",
    "category": "Utility",
    "description": "Minimal compliant PinhOS sandboxed app template",
    "entry": "main",
    "min_sram": 24576,
    "min_block": 16384,
    "needs_radio": False,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": [],
}


def _tok(theme, name, fallback):
    if theme is not None and hasattr(theme, "color"):
        return theme.color(name)
    return fallback


def _draw(board, theme, count):
    c_bg = _tok(theme, "bg", 0)
    c_surf = _tok(theme, "surface", 1)
    c_bdr = _tok(theme, "border", 2)
    c_acc = _tok(theme, "accent", 3)
    c_afg = _tok(theme, "accent_fg", 4)
    c_txt = _tok(theme, "text", 15)
    c_ok = _tok(theme, "ok", 10)

    board.fill(c_bg)
    board.fill_rect(0, 0, 320, 22, c_acc)
    board.text("MY PINHOS APP", 10, 7, c_afg)

    board.fill_rect(12, 40, 296, 160, c_surf)
    board.rect(12, 40, 296, 160, c_bdr)
    board.text("Counter: {}".format(count), 24, 64, c_ok)
    board.text("Press [UP/DOWN] or [SPACE]", 24, 96, c_txt)
    board.text("Press [ESC] to exit cleanly", 24, 120, c_txt)
    board.text("Press [ALT+F5] for OS ANR check", 24, 144, c_txt)

    board.fill_rect(8, 286, 304, 26, c_surf)
    board.rect(8, 286, 304, 26, c_acc)
    board.text("[SPACE]+1  [R]Reset  [ESC]Exit", 28, 295, c_txt)
    board.show()


def main(ctx):
    board = ctx.board
    theme = getattr(ctx, "theme", None)
    if board is None:
        return {"ok": False, "reason": "no_board"}

    state = ctx.load_state(default={"count": 0})
    count = int(state.get("count", 0))
    ctx.log("Started count={}".format(count))

    _draw(board, theme, count)
    if hasattr(board, "clear_input"):
        board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

    try:
        while True:
            if hasattr(ctx, "yield_"):
                ctx.yield_(step_web=True)
            key = poll_fn() if poll_fn else None
            if not key:
                if hasattr(time, "sleep_ms"):
                    time.sleep_ms(30)
                else:
                    time.sleep(0.03)
                continue

            ku = str(key).upper()
            if ku in ("ESC", "Q", "BACK", "BACKSPACE"):
                board.beep(900, 10)
                break
            elif ku in ("SPACE", " ", "UP", "ENTER"):
                count += 1
                board.beep(1300, 10)
                _draw(board, theme, count)
            elif ku == "DOWN":
                count = max(0, count - 1)
                board.beep(1100, 10)
                _draw(board, theme, count)
            elif ku == "R":
                count = 0
                board.beep(1000, 12)
                _draw(board, theme, count)
    finally:
        ctx.save_state({"count": count})
        gc.collect()

    return {"app_id": ctx.app_id, "count": count}

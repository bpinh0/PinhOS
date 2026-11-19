# PinhOS Phase 1 Reference Sandboxed Applet (apps/hello_world.py)

APP_META = {
    "id": "hello_world",
    "name": "Hello PinhOS",
    "version": "1.0.0",
    "category": "System",
    "description": "Reference Phase 1 sandboxed diagnostic applet",
    "entry": "main",
    "min_sram": 16384,
    "ui_modes": ["native"],
    "native_libs": []
}


def main(ctx):
    board = ctx.board
    prev = ctx.load_state(default={"runs": 0})
    runs = int(prev.get("runs", 0)) + 1
    ctx.save_state({"runs": runs})

    if board is not None:
        board.fill(0)
        board.rect(10, 40, 300, 120, 3)
        board.text("PinhOS Sandboxed Applet", 40, 60, 3)
        board.text("App ID : " + ctx.app_id, 40, 84, 15)
        board.text("Runs   : " + str(runs), 40, 104, 10)
        board.fill_rect(10, 276, 300, 30, 8)
        board.rect(10, 276, 300, 30, 3)
        board.text("[ENTER / ESC / Q] Return to OS", 34, 287, 15)
        board.show()

    return {"app_id": ctx.app_id, "runs": runs}

# PinhOS Phase 2 Reference Sandboxed Applet (apps/hello_world.py)

APP_META = {
    "id": "hello_world",
    "name": "Hello PinhOS",
    "version": "1.1.0",
    "category": "System",
    "description": "Theme-aware reference sandboxed diagnostic applet",
    "entry": "main",
    "min_sram": 16384,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": []
}


def _tok(theme, name, fallback):
    if theme is not None and hasattr(theme, "color"):
        return theme.color(name)
    return fallback


def main(ctx):
    board = ctx.board
    theme = getattr(ctx, "theme", None)
    ui = getattr(ctx, "ui", None)
    prev = ctx.load_state(default={"runs": 0})
    runs = int(prev.get("runs", 0)) + 1
    ctx.save_state({"runs": runs})

    theme_name = "Built-in"
    if theme is not None:
        active = getattr(theme, "active", theme)
        theme_name = getattr(active, "name", "Built-in")
    ui_mode = getattr(ui, "mode", "gui").upper() if ui is not None else "GUI"

    if board is not None:
        c_bg = _tok(theme, "bg", 0)
        c_surf = _tok(theme, "surface", 1)
        c_bdr = _tok(theme, "border", 2)
        c_acc = _tok(theme, "accent", 3)
        c_afg = _tok(theme, "accent_fg", 4)
        c_txt = _tok(theme, "text", 15)
        c_muted = _tok(theme, "text_muted", 6)
        c_ok = _tok(theme, "ok", 10)

        board.fill(c_bg)
        board.fill_rect(0, 0, 320, 22, c_acc)
        board.text("HELLO PINHOS [{}]".format(ui_mode), 10, 7, c_afg)

        board.fill_rect(10, 36, 300, 152, c_surf)
        board.rect(10, 36, 300, 152, c_bdr)
        board.text("Sandboxed Applet Active", 22, 48, c_acc)
        board.hline(16, 62, 288, c_bdr)

        board.text("App ID :", 22, 74, c_muted)
        board.text(str(ctx.app_id)[:22], 96, 74, c_txt)
        board.text("Runs   :", 22, 94, c_muted)
        board.text(str(runs), 96, 94, c_ok)
        board.text("Theme  :", 22, 114, c_muted)
        board.text(str(theme_name)[:22], 96, 114, c_acc)
        board.text("UI Mode:", 22, 134, c_muted)
        board.text(ui_mode, 96, 134, c_txt)
        board.text("Status :", 22, 154, c_muted)
        board.text("SANDBOX ISOLATED OK", 96, 154, c_ok)

        board.fill_rect(10, 276, 300, 30, c_surf)
        board.rect(10, 276, 300, 30, c_acc)
        board.text("[ANY KEY] Return to PinhOS", 52, 287, c_txt)
        board.show()

    return {"app_id": ctx.app_id, "runs": runs, "theme": theme_name, "mode": ui_mode}

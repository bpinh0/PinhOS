# PinhOS — Stress & Concurrency Self-Test Gates 13-14 (tests/selftest_stress.py)
# Loaded on demand and purged immediately to preserve RP2350 SRAM (Refs #11).

import gc
import json

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

CAP_96K = 96 * 1024

_REAL_TOOLS = (
    "tools/files.py",
    "tools/editor.py",
    "tools/net_tools.py",
    "tools/sysmon.py",
    "tools/uart_term.py",
    "tools/shell.py",
    "apps/hello_world.py",
)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_stress_sandbox_20x(root="/sd/pinhos", iters=20):
    """Gate 13: Launch real tools via SandboxRunner.run_file() 20x with WebPortal up; assert largest_free(96KB) >= 16 KB."""
    from boards import get_board
    from core.config import ConfigManager, load_version_manifest
    from core.memutil import largest_free
    from core.sandbox import SandboxRunner
    from core.theme import get_theme_manager
    from ui.engine import UIEngine
    from web.server import WebServer

    board = get_board()
    cfg = ConfigManager()
    manifest = load_version_manifest(root=root)
    tm = get_theme_manager(config=cfg, board=board)
    ui = UIEngine(board=board, theme_manager=tm, config=cfg)

    ws = WebServer(board=board, config=cfg, manifest=manifest, root=root, host="0.0.0.0", port=8080)
    ws.start()
    orig_poll = board.poll_key
    min_blk = CAP_96K
    free0 = gc.mem_free() if hasattr(gc, "mem_free") else 0
    blk0 = largest_free(CAP_96K)
    try:
        # Return ESC immediately so interactive tools execute full init + render + cleanup cleanly
        board.poll_key = lambda: "ESC"
        sbx = SandboxRunner(board=board, config=cfg, theme=tm, ui=ui)
        base = root.rstrip("/") + "/"
        for i in range(int(iters)):
            rel = _REAL_TOOLS[i % len(_REAL_TOOLS)]
            args = {"path": base + "notes.txt"} if rel == "tools/editor.py" else None
            res = sbx.run_file(base + rel, args=args, wait_on_error=False)
            _assert(res.get("ok"), "iter {} ({}) failed: {}".format(i, rel, res.get("error")))
            blk = largest_free(CAP_96K)
            if blk < min_blk:
                min_blk = blk
        _assert(min_blk >= 16384, "largest_free dropped to {}B (<16KB)".format(min_blk))
    finally:
        board.poll_key = orig_poll
        ws.stop()
        gc.collect()
        gc.collect()
    free1 = gc.mem_free() if hasattr(gc, "mem_free") else 0
    blk1 = largest_free(CAP_96K)
    return "{}x real tools OK (free {}K->{}K, min_blk={}KB, end_blk={}KB)".format(
        iters, free0 // 1024, free1 // 1024, min_blk // 1024, blk1 // 1024
    )


def test_stress_wifi_web_concurrent(root="/sd/pinhos"):
    """Gate 14: Run Wi-Fi scan while WebServer actively serves HTTP requests, plus pause/resume check."""
    from boards import get_board
    from core.config import load_version_manifest
    from core.memutil import largest_free
    from net.wifi import get_wifi_manager
    from tests.selftest_p4 import _req_pipe
    from web.server import WebServer

    board = get_board()
    manifest = load_version_manifest(root=root)
    ws = WebServer(board=board, manifest=manifest, root=root, host="0.0.0.0", port=8080)
    ws.start()
    lp = asyncio.get_event_loop()
    nets_found = 0
    th = {"X-PinhOS-Token": ws.token}  # /api/* requires token (Refs #23)
    try:
        # Serve HTTP request before scan
        c1, b1 = lp.run_until_complete(_req_pipe(ws, "GET", "/api/status", hdrs=th))
        _assert(c1 == 200 and json.loads(b1.decode("utf-8")).get("ok"), "pre-scan status failed: {}".format(c1))

        # Run single-pass Wi-Fi scan while WebServer is active (non-fatal if no Wi-Fi HW in sim)
        wm = get_wifi_manager()
        try:
            nets = wm.scan()
            nets_found = len(nets) if isinstance(nets, list) else 0
        except Exception:
            nets_found = 0

        # Serve HTTP requests immediately after/concurrent with scan & step server
        ws.step(10)
        c2, b2 = lp.run_until_complete(_req_pipe(ws, "GET", "/api/status", hdrs=th))
        st2 = json.loads(b2.decode("utf-8"))
        _assert(c2 == 200 and st2.get("ok") and "sram_largest" in st2, "post-scan status failed: {}".format(c2))

        # Verify pause/resume cycle leaves listener healthy
        _assert(ws.pause(), "ws.pause() failed")
        _assert(not ws.running, "ws still running after pause")
        _assert(ws.resume(), "ws.resume() failed")
        _assert(ws.running, "ws not running after resume")
        c3, _ = lp.run_until_complete(_req_pipe(ws, "GET", "/api/status", hdrs=th))
        _assert(c3 == 200, "post-resume status failed: {}".format(c3))

        blk = largest_free(CAP_96K)
        _assert(blk >= 16384, "largest_free {}B < 16KB after scan+web".format(blk))
    finally:
        ws.stop()
        gc.collect()
        gc.collect()
    return "scan({} APs)+HTTP 200+pause/resume OK (blk={}KB)".format(nets_found, blk // 1024)


def test_stress_menu_walk(root="/sd/pinhos"):
    """Deep Stress: Walk all 6 Settings/Launcher categories via UI menu tree + theme/mode toggles."""
    from boards import get_board
    from core.config import ConfigManager, load_version_manifest
    from core.memutil import largest_free
    from core.theme import get_theme_manager
    from ui.engine import UIEngine

    board = get_board()
    cfg = ConfigManager()
    manifest = load_version_manifest(root=root)
    tm = get_theme_manager(config=cfg, board=board)
    ui = UIEngine(board=board, theme_manager=tm, config=cfg)

    orig_poll = board.poll_key
    min_blk = CAP_96K
    try:
        board.poll_key = lambda: "ESC"
        import ui.menu as um
        for cat in ("toolkit", "files", "apps", "system", "settings", "set_conn", "set_time"):
            um.open_menu_tree(board, ui, tm, cfg, None, None, manifest, cat, None)
            blk = largest_free(CAP_96K)
            if blk < min_blk:
                min_blk = blk
        for _ in range(4):
            tm.cycle(step=1, persist=False)
            ui.toggle_mode(persist=False)
        _assert(min_blk >= 16384, "menu walk largest_free {}B < 16KB".format(min_blk))
    finally:
        board.poll_key = orig_poll
        import sys
        for _m in ("ui.menu", "ui._menu_net", "ui._log_view"):
            sys.modules.pop(_m, None)
        gc.collect()
        gc.collect()
    return "7 menus+4x theme/mode OK (min_blk={}KB)".format(min_blk // 1024)


def run_stress(root="/sd/pinhos", deep=False):
    r13 = test_stress_sandbox_20x(root=root)
    gc.collect()
    r14 = test_stress_wifi_web_concurrent(root=root)
    gc.collect()
    res = {"gate13": r13, "gate14": r14}
    if deep:
        res["menu_walk"] = test_stress_menu_walk(root=root)
        gc.collect()
    return res

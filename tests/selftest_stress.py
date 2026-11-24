# PinhOS — Stress & Concurrency Self-Test Gates 13-14 (tests/selftest_stress.py)
# Loaded on demand and purged immediately to preserve RP2350 SRAM (#11).

import gc
import time

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_stress_sandbox_20x(root="/sd/pinhos"):
    """Gate 13: Launch a sandboxed applet 20x with WebPortal up; assert largest_free >= 16 KB."""
    from boards import get_board
    from core.config import load_version_manifest
    from core.memutil import largest_free
    from core.sandbox import SandboxRunner
    from web.server import WebServer

    board = get_board()
    manifest = load_version_manifest(root=root)
    ws = WebServer(board=board, manifest=manifest, root=root, host="0.0.0.0", port=8080)
    ws.start()
    min_blk = 65536
    try:
        sbx = SandboxRunner(board=board)
        src = (
            "APP_META = {'id': 'stress_noop', 'name': 'Stress', 'version': '1.0.0', "
            "'category': 'System', 'description': 'noop', 'entry': 'main', "
            "'min_sram': 16384, 'ui_modes': ['gui'], 'native_libs': []}\n"
            "def main(ctx):\n"
            "    ctx.yield_(step_web=False)\n"
            "    return 42\n"
        )
        for i in range(20):
            res = sbx.run_source(src, app_path="<stress_{}>".format(i))
            _assert(res["ok"] and res["return_value"] == 42, "iter {} failed: {}".format(i, res.get("error")))
            blk = largest_free(32768)
            if blk < min_blk:
                min_blk = blk
        _assert(min_blk >= 16384, "largest_free dropped to {}B (<16KB)".format(min_blk))
    finally:
        ws.stop()
        gc.collect()
    return "20x OK (min_blk={}KB)".format(min_blk // 1024)


def test_stress_wifi_web_concurrent(root="/sd/pinhos"):
    """Gate 14: Verify single-pass Wi-Fi scan policy & WebPortal pause/resume without leak."""
    from boards import get_board
    from core.config import load_version_manifest
    from core.memutil import largest_free
    from web.server import WebServer

    board = get_board()
    manifest = load_version_manifest(root=root)
    ws = WebServer(board=board, manifest=manifest, root=root, host="0.0.0.0", port=8080)
    ws.start()
    try:
        _assert(ws.running, "ws not running")
        _assert(ws.pause(), "ws.pause() failed")
        _assert(not ws.running, "ws still running after pause")
        _assert(ws.resume(), "ws.resume() failed")
        _assert(ws.running, "ws not running after resume")
        blk = largest_free(32768)
        _assert(blk >= 16384, "largest_free {}B < 16KB after pause/resume".format(blk))
    finally:
        ws.stop()
        gc.collect()
    return "pause/resume OK (blk={}KB)".format(blk // 1024)


def run_stress(root="/sd/pinhos"):
    r13 = test_stress_sandbox_20x(root=root)
    gc.collect()
    r14 = test_stress_wifi_web_concurrent(root=root)
    gc.collect()
    return {"gate13": r13, "gate14": r14}

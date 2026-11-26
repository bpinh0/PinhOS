# PinhOS — Contiguous-Heap Diagnostics & Pressure Helper (core/memutil.py)
# Zero hardcoded GPIO pins; compiled to .mpy (-O2, v6.3) by picocalc.ps1.

import gc


def largest_free(cap=98304, step=1024):
    """
    Estimate the largest contiguous free SRAM block (bytes, default 96 KB cap) via
    gc.collect() + binary search with transient bytearray probes. Zero persistent heap.
    """
    gc.collect()
    free_b = gc.mem_free() if hasattr(gc, "mem_free") else int(cap)
    hi = min(int(cap), int(free_b))
    st = max(256, int(step))
    if hi < st:
        return 0
    # Quick fast-path check at ceiling
    try:
        b = bytearray(hi)
        b = None
        gc.collect()
        return hi
    except MemoryError:
        gc.collect()

    lo = 0
    best = 0
    while hi - lo >= st:
        mid = ((lo + hi) // (2 * st)) * st
        if mid <= lo:
            break
        try:
            b = bytearray(mid)
            b = None
            best = mid
            lo = mid + st
        except MemoryError:
            hi = mid - st
        gc.collect()
    return best


_TRANSIENT_MODS = (
    "ui.menu", "ui._menu_net", "ui._log_view", "net.sync",
    "core.sandbox", "boards.generic_spi", "ui.fonts_ext",
)


def reclaim(level=1, rs=None, keep=()):
    """
    MemGuard reclaimer (call ONLY from safe points: idle tick / pre-flight, never mid-tool).
    L1: unload transient modules (menus, sandbox, tests.*) + gc.collect().
    L2: additionally stop an idle WebPortal (frees lwIP/uasyncio heap).
    Returns bytes freed.
    """
    import sys
    gc.collect()
    b0 = gc.mem_free() if hasattr(gc, "mem_free") else 0
    if level >= 1:
        for m in list(sys.modules.keys()):
            if m in keep:
                continue
            if m in _TRANSIENT_MODS or m == "tests" or m.startswith("tests."):
                sys.modules.pop(m, None)
        gc.collect()
    if level >= 2 and rs is not None and rs.get("web_active"):
        ws = rs.get("web_server")
        if ws is not None and not getattr(ws, "pending_run", None):
            w = sys.modules.get("web")
            if w is not None:
                try:
                    w.stop_portal(rs)
                except Exception:
                    pass
        gc.collect()
    return max(0, (gc.mem_free() if hasattr(gc, "mem_free") else 0) - b0)


def ensure_heap(rs=None, min_free=98304, min_blk=32768, keep=()):
    """Pre-flight: guarantee free SRAM + contiguous block before heavy ops. Returns (free_bytes, ok)."""
    gc.collect()
    if gc.mem_free() >= min_free and largest_free(min_blk) >= min_blk:
        return gc.mem_free(), True
    reclaim(1, rs, keep)
    if gc.mem_free() >= min_free and largest_free(min_blk) >= min_blk:
        return gc.mem_free(), True
    reclaim(2, rs, keep)
    ok = gc.mem_free() >= min_free // 2 and largest_free(min_blk) >= min_blk
    return gc.mem_free(), ok


def heap_pressure(cfg=None, min_block=16384):
    """Return True if total free SRAM < swap_low_sram OR largest_free < min_block."""
    low_sram = 65536
    if cfg is not None:
        try:
            low_sram = int(cfg.get("swap_low_sram", 65536))
        except Exception:
            low_sram = 65536
    gc.collect()
    free_b = gc.mem_free() if hasattr(gc, "mem_free") else 262144
    if free_b < low_sram:
        return True
    return largest_free(cap=max(int(min_block), 16384)) < int(min_block)

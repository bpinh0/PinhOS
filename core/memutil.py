# PinhOS — Contiguous-Heap Diagnostics & Pressure Helper (core/memutil.py)
# Zero hardcoded GPIO pins; compiled to .mpy (-O2, v6.3) by picocalc.ps1.

import gc


def largest_free(cap=32768, step=1024):
    """
    Estimate the largest contiguous free SRAM block (bytes) via gc.collect() +
    binary search with transient bytearray probes. Leaves zero persistent heap.
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

# PinhOS Frozen Early Boot (_boot.py) — RP2350 PicoCalc Custom UF2
# Runs before mp_usbd_init(): sets up flash, PicoCalc display/keyboard/SD, and UART0 COM4.
# Returns cleanly so ports/rp2/main.c finishes USB/REPL init before invoking pinhos_boot.py.

import gc
import os
import sys
import time
import machine

# 1. Try mounting internal flash LittleFS2 if available (non-fatal if unmounted/locked)
try:
    import rp2
    bdev = rp2.Flash()
    try:
        vfs = os.VfsLfs2(bdev, progsize=256)
        os.mount(vfs, "/")
    except Exception:
        pass
except Exception:
    pass

# 2. Initialize PicoCalc display, keyboard, SPI0 microSD (/sd), and VT terminal
try:
    import picocalc
    from picocalc import PicoDisplay, PicoKeyboard, PicoSD
    import vt

    pc_display = PicoDisplay(320, 320)
    pc_keyboard = PicoKeyboard()
    pc_sd = PicoSD()
    for _ in range(3):
        try:
            pc_sd.mount()
            os.listdir("/sd")
            break
        except Exception:
            time.sleep_ms(100)
    pc_terminal = vt.vt(pc_display, pc_keyboard, sd=pc_sd())

    picocalc.display = pc_display
    picocalc.keyboard = pc_keyboard
    picocalc.terminal = pc_terminal
    picocalc.sd = pc_sd
except Exception as _hw_exc:
    print("[PinhOS] PicoCalc HW init err:", repr(_hw_exc))

# 3. Attach UART(0) GP0/GP1 (CH340 COM4) to os.dupterm slot 0 for instant serial REPL
try:
    _u0 = machine.UART(0, 115200, rxbuf=4096)
    os.dupterm(_u0, 0)
except Exception:
    pass

# 4. Ensure /sd/pinhos is first on sys.path (ahead of /sd and /)
for _p in ("/", "/sd", "/sd/pinhos"):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

gc.collect()

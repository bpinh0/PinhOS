# PinhOS Phase 1 — Abstract Hardware Abstraction Layer (boards/base.py)
# Zero hardcoded pin numbers, bus IDs, or I2C addresses belong in this module.

import time

# Capability bitflags
CAP_DISPLAY      = 1 << 0
CAP_KEYBOARD     = 1 << 1
CAP_POINTER      = 1 << 2
CAP_SDCARD       = 1 << 3
CAP_BATTERY      = 1 << 4
CAP_BACKLIGHT    = 1 << 5
CAP_KB_BACKLIGHT = 1 << 6
CAP_AUDIO        = 1 << 7
CAP_RTC          = 1 << 8
CAP_WIFI         = 1 << 9
CAP_BLE          = 1 << 10

# Keyboard modifier bitflags
MOD_NONE  = 0
MOD_SHIFT = 1 << 0
MOD_CTRL  = 1 << 1
MOD_ALT   = 1 << 2
MOD_SYM   = 1 << 3
MOD_META  = 1 << 4

__all__ = [
    "BoardBase",
    "CAP_DISPLAY",
    "CAP_KEYBOARD",
    "CAP_POINTER",
    "CAP_SDCARD",
    "CAP_BATTERY",
    "CAP_BACKLIGHT",
    "CAP_KB_BACKLIGHT",
    "CAP_AUDIO",
    "CAP_RTC",
    "CAP_WIFI",
    "CAP_BLE",
    "MOD_NONE",
    "MOD_SHIFT",
    "MOD_CTRL",
    "MOD_ALT",
    "MOD_SYM",
    "MOD_META",
    "rgb565",
    "rgb565_swap",
]


def rgb565(r, g, b):
    """Pack 8-bit R, G, B into standard 16-bit RGB565 integer."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)


def rgb565_swap(r, g, b):
    """Pack 8-bit R, G, B into byte-swapped 16-bit RGB565 for big-endian SPI DMA."""
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
    return ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)


class BoardBase:
    """
    Abstract Hardware Contract for all PinhOS target boards.
    Subclasses encapsulate all board-specific pins, buses, and peripherals.
    """

    id = "base"
    name = "Abstract PinhOS Board"
    capabilities = 0
    display_width = 320
    display_height = 320
    color_depth = 16

    def __init__(self, config=None):
        self.config = config or {}
        self.initialized = False
        self._input_queue = []
        self._max_queue = 32
        self._modifiers = MOD_NONE
        self._backlight_pct = int(self.config.get("lcd_brightness", 80))
        self._kb_backlight_pct = int(self.config.get("kb_brightness", 60))
        self._sd_mounted = False
        self._sd_mount_point = "/sd"
        self._font_name = "default"
        self._font_mv = None

    # --- Lifecycle & Capabilities ---

    def has_capability(self, flag):
        return bool(self.capabilities & flag)

    def init(self):
        """Initialize board peripherals (display, input, RTC, backlights)."""
        self.initialized = True
        return True

    def deinit(self):
        """Release board peripherals cleanly."""
        self.stop_audio()
        self.clear_input()
        self.initialized = False

    def restore_state(self):
        """
        Restore display refresh, LUT palette, audio silence, and input queue
        after a sandboxed app exits or faults.
        """
        self.stop_audio()
        self.clear_input()
        self.recover_refresh()

    # --- Display Contract (320x320 RGB565 / Indexed LUT) ---

    def fill(self, color=0):
        raise NotImplementedError

    def fill_rect(self, x, y, w, h, color):
        raise NotImplementedError

    def rect(self, x, y, w, h, color):
        raise NotImplementedError

    def hline(self, x, y, w, color):
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.fill_rect(x, y, 1, h, color)

    def line(self, x0, y0, x1, y1, color):
        # Bresenham fallback if subclass does not override
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def pixel(self, x, y, color):
        self.fill_rect(x, y, 1, 1, color)

    def text(self, s, x, y, color=15):
        raise NotImplementedError

    def blit(self, buf, x, y, w, h, fmt="RGB565"):
        """Blit raw pixel buffer (RGB565 or 4-bit indexed) to (x, y, w, h)."""
        raise NotImplementedError

    def set_lut(self, lut):
        """Apply 16-entry RGB565 Look-Up Table for 4-bit native mode."""
        pass

    def reset_default_lut(self):
        """Restore built-in factory 16-entry RGB565 LUT (e.g. for BSOD/Recovery)."""
        self._font_name = "default"
        self._font_mv = None

    def set_font(self, font_name="default", font_mv=None):
        """Set active 6x8 bitmap font ('default', 'bold', 'retro', or custom 570B memoryview)."""
        self._font_name = str(font_name or "default").strip().lower()
        self._font_mv = font_mv
        return self._font_name

    def get_font_name(self):
        return self._font_name

    def show(self):
        """Flush framebuffer to physical display if manual refresh is active."""
        pass

    def stop_refresh(self):
        """Pause background Core 1 DMA refresh (e.g. before SPI/Wi-Fi operations)."""
        pass

    def recover_refresh(self):
        """Resume background Core 1 DMA refresh."""
        pass

    # --- Input Queue Contract (Keyboard & Pointer) ---

    def poll_input(self):
        """Poll hardware keyboard/pointer and enqueue events. Returns new event count."""
        return 0

    def push_event(self, event):
        """Push an input event dict onto the bounded input queue."""
        if not isinstance(event, dict):
            return
        if len(self._input_queue) >= self._max_queue:
            self._input_queue.pop(0)
        self._input_queue.append(event)

    def get_event(self):
        """Pop the next input event dict from the queue, polling hardware first if empty."""
        if not self._input_queue:
            self.poll_input()
        if self._input_queue:
            evt = self._input_queue.pop(0)
            if isinstance(evt, dict) and "modifiers" in evt:
                self._modifiers = int(evt["modifiers"])
            return evt
        return None

    def read_key(self):
        """Return the next key string (e.g. 'UP', 'ENTER', 'F1', 'A') or None."""
        evt = self.get_event()
        if evt and evt.get("type") == "key":
            return evt.get("key")
        return None

    def poll_key(self):
        """Non-blocking key poll returning the next key string or None."""
        return self.read_key()

    def get_modifiers(self):
        """Return active modifier bitmask (MOD_SHIFT | MOD_CTRL | MOD_ALT | MOD_SYM)."""
        return self._modifiers

    def clear_input(self):
        """Clear queued input events and reset transient modifiers."""
        self._input_queue.clear()
        self._modifiers = MOD_NONE

    # --- SPI microSD Storage Contract ---

    def is_sd_mounted(self, mount_point="/sd"):
        raise NotImplementedError

    def mount_sd(self, mount_point="/sd", retries=3):
        raise NotImplementedError

    def unmount_sd(self, mount_point="/sd"):
        raise NotImplementedError

    def get_sd_stats(self, mount_point="/sd"):
        import os
        if not self.is_sd_mounted(mount_point):
            return {"mounted": False, "total_kb": 0, "free_kb": 0}
        try:
            st = os.statvfs(mount_point)
            block_size = st[0]
            total_kb = (block_size * st[2]) // 1024
            free_kb = (block_size * st[3]) // 1024
            return {"mounted": True, "total_kb": total_kb, "free_kb": free_kb}
        except Exception:
            return {"mounted": True, "total_kb": 0, "free_kb": 0}

    # --- Power & Battery Telemetry Contract ---

    def get_battery(self):
        """
        Return battery status dictionary:
        {"percent": int(0..100), "voltage_mv": int, "charging": bool, "present": bool}
        """
        return {
            "percent": 100,
            "voltage_mv": 4200,
            "charging": False,
            "present": False,
        }

    # --- PWM Backlight Contract (0..100%) ---

    def set_backlight(self, percent):
        self._backlight_pct = max(0, min(100, int(percent)))
        return True

    def get_backlight(self):
        return self._backlight_pct

    def set_kb_backlight(self, percent):
        self._kb_backlight_pct = max(0, min(100, int(percent)))
        return True

    def get_kb_backlight(self):
        return self._kb_backlight_pct

    # --- Audio / Buzzer Contract ---

    def beep(self, freq=1200, duration_ms=20, volume=50):
        return False

    def play_audio(self, path):
        """Start non-blocking chunked PCM WAV playback from SD path. Returns True on success."""
        return False

    def step_audio(self):
        """Cooperatively feed one pre-allocated PCM chunk to PWM audio. Returns True while playing."""
        return False

    def stop_audio(self):
        pass

    def audio_playing(self):
        """Return True if a non-blocking audio stream is currently active."""
        return False

    def audio_status(self):
        """Return compact dict with playback state, elapsed/total seconds, and last error."""
        return {"playing": False, "pos_s": 0, "dur_s": 0, "rate": 0, "ch": 0, "bits": 0, "error": ""}

    # --- RTC & System Telemetry Contract ---

    def get_rtc_datetime(self):
        """Return 8-tuple (year, month, day, weekday, hour, minute, second, subseconds)."""
        try:
            import machine
            return machine.RTC().datetime()
        except Exception:
            t = time.localtime()
            return (t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0)

    def set_rtc_datetime(self, dt_tuple):
        try:
            import machine
            machine.RTC().datetime(dt_tuple)
            return True
        except Exception:
            return False

    def get_timestamp_str(self, short=False):
        try:
            dt = self.get_rtc_datetime()
            # machine.RTC().datetime() -> (year, month, day, weekday, hour, minute, second, sub)
            if short:
                return "{:02d}:{:02d}:{:02d}".format(dt[4], dt[5], dt[6])
            return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                dt[0], dt[1], dt[2], dt[4], dt[5], dt[6]
            )
        except Exception:
            return "00:00:00" if short else "2026-01-01 00:00:00"

    def get_cpu_temp_c(self):
        return 28.0

    def get_cpu_freq_mhz(self):
        """Return active CPU clock frequency in MHz."""
        try:
            import machine
            return int(machine.freq() // 1000000)
        except Exception:
            return int(self.config.get("cpu_freq_mhz", 150))

    def capture_screenshot(self, path=None):
        """Capture framebuffer screenshot via board driver and return saved path or None."""
        if hasattr(self, "screenshot"):
            return self.screenshot(path=path)
        return None

    def reboot(self):
        """Persist RTC state if mounted and perform a clean hardware reset via board HAL."""
        try:
            from core.config import save_rtc_state
            save_rtc_state(self)
        except Exception:
            pass
        try:
            import machine
            machine.reset()
        except Exception:
            pass

    # --- Read-only Bus Diagnostics (Phase 3 field tools: hwinfo / i2cscan) ---

    def i2c_scan(self):
        """Return a sorted list of responding 7-bit I2C addresses (read-only probe)."""
        return []

    def get_i2c_known(self):
        """Return {addr: label} for board-known I2C peripherals (labels live in boards/)."""
        return {}

    def get_bus_info(self):
        """Return a dict summarising bus/peripheral state: {'i2c': bool, 'uart': bool, 'sd': bool}."""
        return {"i2c": False, "uart": False, "sd": bool(self._sd_mounted)}

    def open_aux_uart(self, baud=115200, bits=8, parity=None, stop=1):
        """Open auxiliary field UART (never UART0 COM4 REPL). Subclasses override."""
        return None

    def close_aux_uart(self):
        """Close auxiliary field UART if open."""
        pass

    def ensure_serial_repl(self):
        """Ensure board serial REPL bridge (dupterm) is active. Subclasses override."""
        return None

    def set_serial_link(self, enabled):
        """Enable or lock the board's host serial link (COM4 UART0 dupterm). Subclasses override."""
        return bool(enabled)

    def serial_print(self, *args):
        """Write diagnostic line to board serial console cleanly."""
        print(" ".join(str(a) for a in args))

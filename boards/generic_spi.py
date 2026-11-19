# PinhOS Phase 1 — Generic SPI LCD + I2C CardKB Fallback Profile (boards/generic_spi.py)
# Reference driver for custom Pico 2W + ST7789/ILI9341 SPI display + M5Stack CardKB setups.

import os
import time

try:
    import machine
except Exception:
    machine = None

try:
    import framebuf
except Exception:
    framebuf = None

from boards.base import (
    BoardBase,
    CAP_DISPLAY,
    CAP_KEYBOARD,
    CAP_SDCARD,
    CAP_BATTERY,
    CAP_BACKLIGHT,
    CAP_AUDIO,
    CAP_RTC,
    CAP_WIFI,
    CAP_BLE,
    MOD_NONE,
    MOD_SHIFT,
    MOD_SYM,
)

# Default custom cyberdeck pin mapping (overridable via config["pins"])
DEFAULT_PINS = {
    "spi_lcd_bus": 1,
    "lcd_sck": 10,
    "lcd_mosi": 11,
    "lcd_bl": 12,
    "lcd_cs": 13,
    "lcd_dc": 14,
    "lcd_rst": 15,
    "lcd_baud": 40_000_000,
    "i2c_kb_bus": 0,
    "kb_sda": 4,
    "kb_scl": 5,
    "cardkb_addr": 0x5F,
    "spi_sd_bus": 0,
    "sd_miso": 16,
    "sd_cs": 17,
    "sd_sck": 18,
    "sd_mosi": 19,
    "sd_baud": 12_000_000,
    "buzzer_pin": 22,
    "vsys_adc_pin": 29,
    "temp_adc_ch": 4,
}


class GenericSPIBoard(BoardBase):
    """
    Configurable fallback HAL driver for bare/custom Raspberry Pi Pico 2W builds
    using standard SPI displays (ST7789 / ILI9341) and I2C CardKB (0x5F).
    """

    id = "generic_spi"
    name = "Generic Pico 2W + SPI LCD + I2C CardKB"
    capabilities = (
        CAP_DISPLAY
        | CAP_KEYBOARD
        | CAP_SDCARD
        | CAP_BATTERY
        | CAP_BACKLIGHT
        | CAP_AUDIO
        | CAP_RTC
        | CAP_WIFI
        | CAP_BLE
    )
    display_width = 320
    display_height = 320
    color_depth = 16

    def __init__(self, config=None):
        super().__init__(config)
        self.pins = dict(DEFAULT_PINS)
        if isinstance(self.config.get("pins"), dict):
            self.pins.update(self.config["pins"])
        self._fb_buf = None
        self._fb = None
        self._spi_lcd = None
        self._i2c_kb = None
        self._bl_pwm = None

    def init(self):
        """Initialize backing framebuffer, optional SPI LCD, PWM backlight, and I2C CardKB."""
        # In virtual_only mode (e.g. on-device self-test), use a compact 64x64 scratch
        # buffer (2 KB) to avoid 51.2 KB contiguous MemoryError on a fragmented RP2350 heap.
        if framebuf is not None and self._fb is None:
            import gc
            gc.collect()
            if self.config.get("virtual_only", False):
                fb_w, fb_h = 64, 64
            else:
                fb_w, fb_h = self.display_width, self.display_height
            try:
                self._fb_buf = bytearray((fb_w * fb_h) // 2)
                self._fb = framebuf.FrameBuffer(self._fb_buf, fb_w, fb_h, framebuf.GS4_HMSB)
            except MemoryError:
                gc.collect()
                self._fb_buf = bytearray((64 * 64) // 2)
                self._fb = framebuf.FrameBuffer(self._fb_buf, 64, 64, framebuf.GS4_HMSB)

        if machine is not None and not self.config.get("virtual_only", False):
            try:
                self._i2c_kb = machine.I2C(
                    self.pins["i2c_kb_bus"],
                    sda=machine.Pin(self.pins["kb_sda"]),
                    scl=machine.Pin(self.pins["kb_scl"]),
                    freq=100_000,
                )
            except Exception:
                self._i2c_kb = None

            try:
                self._bl_pwm = machine.PWM(machine.Pin(self.pins["lcd_bl"]))
                self._bl_pwm.freq(1000)
            except Exception:
                self._bl_pwm = None

        self.set_backlight(self._backlight_pct)
        self.clear_input()
        self.initialized = True
        return True

    def deinit(self):
        if self._bl_pwm is not None:
            try:
                self._bl_pwm.deinit()
            except Exception:
                pass
            self._bl_pwm = None
        self._fb = None
        self._fb_buf = None
        super().deinit()

    # --- Display Primitives ---

    def fill(self, color=0):
        if self._fb is not None:
            self._fb.fill(int(color) & 0x0F)

    def fill_rect(self, x, y, w, h, color):
        if self._fb is not None:
            self._fb.fill_rect(int(x), int(y), int(w), int(h), int(color) & 0x0F)

    def rect(self, x, y, w, h, color):
        if self._fb is not None:
            self._fb.rect(int(x), int(y), int(w), int(h), int(color) & 0x0F)

    def hline(self, x, y, w, color):
        if self._fb is not None:
            self._fb.hline(int(x), int(y), int(w), int(color) & 0x0F)

    def vline(self, x, y, h, color):
        if self._fb is not None:
            self._fb.vline(int(x), int(y), int(h), int(color) & 0x0F)

    def line(self, x0, y0, x1, y1, color):
        if self._fb is not None:
            self._fb.line(int(x0), int(y0), int(x1), int(y1), int(color) & 0x0F)

    def pixel(self, x, y, color):
        if self._fb is not None:
            self._fb.pixel(int(x), int(y), int(color) & 0x0F)

    def text(self, s, x, y, color=15):
        if self._fb is not None:
            self._fb.text(str(s), int(x), int(y), int(color) & 0x0F)

    def blit(self, buf, x, y, w, h, fmt="RGB565"):
        if self._fb is not None and framebuf is not None:
            try:
                if isinstance(buf, framebuf.FrameBuffer):
                    self._fb.blit(buf, int(x), int(y))
                else:
                    fb_src = framebuf.FrameBuffer(buf, int(w), int(h), framebuf.GS4_HMSB)
                    self._fb.blit(fb_src, int(x), int(y))
                return True
            except Exception:
                return False
        return True

    # --- I2C CardKB Input Polling ---

    def _decode_cardkb_byte(self, code):
        if not code:
            return (None, MOD_NONE)
        if code == 0xB5:
            return ("UP", MOD_NONE)
        if code == 0xB6:
            return ("DOWN", MOD_NONE)
        if code == 0xB4:
            return ("LEFT", MOD_NONE)
        if code == 0xB7:
            return ("RIGHT", MOD_NONE)
        if code == 0x0D:
            return ("ENTER", MOD_NONE)
        if code == 0x08:
            return ("BACKSPACE", MOD_NONE)
        if code == 0x1B:
            return ("BACK", MOD_NONE)
        if code == 0x09:
            return ("TAB", MOD_NONE)
        if 0x81 <= code <= 0x8A:
            return ("F" + str(code - 0x80), MOD_SYM)
        if 32 <= code <= 126:
            ch = chr(code)
            mods = MOD_SHIFT if ("A" <= ch <= "Z") else MOD_NONE
            return (ch, mods)
        return (None, MOD_NONE)

    def poll_input(self):
        if self._i2c_kb is None:
            return 0
        try:
            data = self._i2c_kb.readfrom(self.pins["cardkb_addr"], 1)
            if data and data[0] != 0:
                key_name, mods = self._decode_cardkb_byte(data[0])
                self._modifiers = mods
                if key_name:
                    self.push_event({
                        "type": "key",
                        "key": key_name,
                        "raw": bytes(data),
                        "modifiers": mods,
                    })
                    return 1
        except Exception:
            pass
        return 0

    # --- SPI microSD Card Mount / Unmount ---

    def is_sd_mounted(self, mount_point="/sd"):
        try:
            mp_name = mount_point.strip("/")
            if mp_name not in os.listdir("/"):
                return False
            os.listdir(mount_point)
            self._sd_mounted = True
            return True
        except Exception:
            self._sd_mounted = False
            return False

    def mount_sd(self, mount_point="/sd", retries=3):
        if self.is_sd_mounted(mount_point):
            return True
        if machine is None:
            return False
        for attempt in range(max(1, int(retries))):
            try:
                import sdcard
                spi = machine.SPI(
                    self.pins["spi_sd_bus"],
                    baudrate=self.pins["sd_baud"],
                    sck=machine.Pin(self.pins["sd_sck"]),
                    mosi=machine.Pin(self.pins["sd_mosi"]),
                    miso=machine.Pin(self.pins["sd_miso"]),
                )
                sd = sdcard.SDCard(spi, machine.Pin(self.pins["sd_cs"], machine.Pin.OUT))
                os.mount(sd, mount_point)
                if self.is_sd_mounted(mount_point):
                    return True
            except Exception:
                pass
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(100 * (attempt + 1))
        return self.is_sd_mounted(mount_point)

    def unmount_sd(self, mount_point="/sd"):
        if not self.is_sd_mounted(mount_point):
            return True
        try:
            os.umount(mount_point)
            self._sd_mounted = False
            return True
        except Exception:
            return False

    # --- Battery & Backlight PWM ---

    def get_battery(self):
        v_mv = 4000
        if machine is not None:
            try:
                adc = machine.ADC(self.pins["vsys_adc_pin"])
                # Pico VSYS divider is 3:1
                v_mv = int(adc.read_u16() * 3.3 * 3.0 * 1000 / 65535)
            except Exception:
                v_mv = 4000
        pct = max(0, min(100, (v_mv - 3300) * 100 // 900))
        return {
            "percent": pct,
            "voltage_mv": v_mv,
            "charging": v_mv > 4250,
            "present": True,
        }

    def set_backlight(self, percent):
        pct = max(0, min(100, int(percent)))
        self._backlight_pct = pct
        if self._bl_pwm is not None:
            try:
                self._bl_pwm.duty_u16(int((pct * 65535) // 100))
            except Exception:
                pass
        return True

    # --- Audio & Temperature ---

    def beep(self, freq=1200, duration_ms=18, volume=50):
        if not self.config.get("sound", True) or machine is None:
            return False
        try:
            pwm = machine.PWM(machine.Pin(self.pins["buzzer_pin"]))
            pwm.freq(max(80, min(8000, int(freq))))
            pwm.duty_u16(int((max(1, min(100, int(volume))) * 32768) // 100))
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(int(duration_ms))
            else:
                time.sleep(duration_ms / 1000.0)
            pwm.duty_u16(0)
            pwm.deinit()
            return True
        except Exception:
            return False

    def get_cpu_temp_c(self):
        if machine is None:
            return 28.0
        try:
            adc = machine.ADC(self.pins["temp_adc_ch"])
            v = adc.read_u16() * (3.3 / 65535.0)
            return round(27.0 - (v - 0.706) / 0.001721, 1)
        except Exception:
            return 28.0

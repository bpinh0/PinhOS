# PinhOS Phase 1 — ClockworkPi PicoCalc Hardware Driver (boards/picocalc.py)
# Encapsulates all PicoCalc (RP2350 Pico 2W + STM32 Southbridge + 320x320 SPI LCD + SPI SD) pins & buses.

import os
import sys
import time
import array

try:
    import machine
except Exception:
    machine = None

try:
    import framebuf
except Exception:
    framebuf = None

try:
    import picocalc as _hw_picocalc
except Exception:
    _hw_picocalc = None

try:
    import uselect as _select_mod
except Exception:
    try:
        import select as _select_mod
    except Exception:
        _select_mod = None

from boards.base import (
    BoardBase,
    CAP_DISPLAY,
    CAP_KEYBOARD,
    CAP_POINTER,
    CAP_SDCARD,
    CAP_BATTERY,
    CAP_BACKLIGHT,
    CAP_KB_BACKLIGHT,
    CAP_AUDIO,
    CAP_RTC,
    CAP_WIFI,
    CAP_BLE,
    MOD_NONE,
    MOD_SHIFT,
    MOD_CTRL,
    MOD_ALT,
    MOD_SYM,
    rgb565_swap,
)

# --- ClockworkPi PicoCalc Hardware Pin & Bus Definitions ---
# Display: SPI1 320x320 IPS LCD (ILI9488 / ST7365P RGB565 / 4-bit LUT)
SPI_LCD_BUS  = 1
PIN_LCD_SCK  = 10
PIN_LCD_MOSI = 11
PIN_LCD_CS   = 13
PIN_LCD_DC   = 14
PIN_LCD_RST  = 15
LCD_BAUDRATE = 40_000_000

# Southbridge: I2C1 STM32F103R8T6 Keyboard & PMU Controller
I2C_SB_BUS       = 1
PIN_SB_SDA       = 6
PIN_SB_SCL       = 7
I2C_SB_FREQ      = 100_000
SB_I2C_ADDR      = 0x1F

# STM32 Southbridge Registers
REG_SB_ID        = 0x01
REG_SB_FW_VER    = 0x02
REG_SB_KEY_CNT   = 0x04
REG_SB_LCD_BKL   = 0x05
REG_SB_KB_FIFO   = 0x09
REG_SB_KB_BKL    = 0x0A
REG_SB_BATTERY   = 0x0B

# Storage: SPI0 Full-Size microSD Card Slot
SPI_SD_BUS   = 0
PIN_SD_MISO  = 16
PIN_SD_CS    = 17
PIN_SD_SCK   = 18
PIN_SD_MOSI  = 19
SD_BAUDRATE  = 25_000_000
SD_BAUDRATE_FALLBACK = 12_000_000

# Audio: Dual PWM Piezo / Speaker Outputs (RP2350 PWM Slice 5: GP26=ChA, GP27=ChB)
PIN_AUDIO_L  = 26
PIN_AUDIO_R  = 27
_RP2350_PWM5_CC  = 0x400A8070
_RP2350_PWM5_TOP = 0x400A8074
_RP2350_DMA_TMR0 = 0x50000420

# Serial Bridge: UART0 (COM4 dupterm) & Auxiliary Field Console: UART1 (side header)
UART_BRIDGE_BUS = 0
PIN_UART_TX     = 0
PIN_UART_RX     = 1
UART_BAUDRATE   = 115200

UART_AUX_BUS    = 1
PIN_AUX_UART_TX = 8
PIN_AUX_UART_RX = 9

# RP2350 Internal Die Temperature ADC Channel
ADC_TEMP_CH = 4


def _build_default_lut():
    """Precompute 16-entry RGB565 Look-Up Table for PinhOS Native Mode."""
    return array.array("H", [
        rgb565_swap(10, 10, 12),     # 0: Pitch Black (#0A0A0C)
        rgb565_swap(200, 30, 30),    # 1: Dark Red
        rgb565_swap(0, 160, 50),     # 2: Matrix Dark Green
        rgb565_swap(255, 176, 0),    # 3: Amber Phosphor (#FFB000)
        rgb565_swap(20, 60, 200),    # 4: Recovery / BSOD Blue
        rgb565_swap(180, 30, 180),   # 5: Purple
        rgb565_swap(153, 106, 0),    # 6: Muted Amber (#996A00)
        rgb565_swap(160, 160, 160),  # 7: Light Gray
        rgb565_swap(45, 48, 54),     # 8: Surface Dark Gray
        rgb565_swap(255, 42, 85),    # 9: Error Red (#FF2A55)
        rgb565_swap(57, 255, 20),    # 10: OK Neon Green (#39FF14)
        rgb565_swap(255, 149, 0),    # 11: Warn Orange (#FF9500)
        rgb565_swap(60, 140, 255),   # 12: Bright Blue
        rgb565_swap(255, 70, 210),   # 13: Synthwave Magenta
        rgb565_swap(0, 229, 255),    # 14: Cyber Cyan (#00E5FF)
        rgb565_swap(255, 255, 255),  # 15: Crisp White
    ])


class PicoCalcBoard(BoardBase):
    """Hardware Abstraction Layer implementation for the ClockworkPi PicoCalc."""

    id = "picocalc"
    name = "ClockworkPi PicoCalc (RP2350 Pico 2W)"
    capabilities = (
        CAP_DISPLAY
        | CAP_KEYBOARD
        | CAP_POINTER
        | CAP_SDCARD
        | CAP_BATTERY
        | CAP_BACKLIGHT
        | CAP_KB_BACKLIGHT
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
        self._hw = _hw_picocalc
        self._disp = None
        self._kb = None
        self._i2c = None
        self._uart = None
        self._serial_link_enabled = True
        self._aux_uart = None
        self._stdin_poll = None
        self._kbuf = bytearray(8)
        self._lut = _build_default_lut()
        # Core 1 auto-refresh is already active from UF2 cold boot; only call recoverRefresh()
        # if stop_refresh() was explicitly called (repeated recoverRefresh() wedges Core 1 on RP2350).
        import sys as _sys
        self._refresh_active = not bool(_sys.modules.get("__pinhos_disp_stopped__"))
        self._fb_buf = None
        self._fb = None
        self.last_screenshot = None
        self.pending_screenshot = None
        self._bat_cache = {
            "percent": 100,
            "voltage_mv": 4150,
            "charging": False,
            "present": True,
        }
        self._last_bat_ms = 0
        self._last_bl_set_ms = 0
        self._last_bl_poll_ms = 0
        self._last_hw_bl = None
        self._bl_scale = 255
        self._sd_spi_boosted = False
        # Cooperative PWM WAV audio streaming state (zero per-chunk heap allocation)
        self._aud_f = None
        self._aud_pwm_l = None
        self._aud_pwm_r = None
        self._aud_rate = 0
        self._aud_ch = 1
        self._aud_bits = 8
        self._aud_rem = 0
        self._aud_buf = None
        self._aud_mv = None
        self._aud_total = 0
        self._aud_bps = 1
        self._aud_us = 125
        self._aud_top = 0
        self._aud_dma = None
        self._aud_ctrl = 0
        self._aud_dma_bufs = None
        self._aud_cur = 0
        self._aud_next_cnt = 0
        self._aud_pack = None
        self._aud_feed = None
        self._aud_err = ""

    def init(self):
        """Initialize PicoCalc display, STM32 I2C southbridge, backlights, and SD card."""
        if self._hw is not None:
            self._disp = getattr(self._hw, "display", None)
            self._kb = getattr(self._hw, "keyboard", None)

        # Initialize fallback framebuffer if running without native picocalc.display
        if self._disp is None and framebuf is not None:
            self._fb_buf = bytearray((self.display_width * self.display_height) // 2)
            self._fb = framebuf.FrameBuffer(
                self._fb_buf,
                self.display_width,
                self.display_height,
                framebuf.GS4_HMSB,
            )

        # Always ensure I2C1 bus handle to STM32 southbridge (0x1F on GP6/GP7) is available.
        # Reuse existing i2c instance from picocalc.keyboard if exposed, else open I2C(1).
        if self._kb is not None and hasattr(self._kb, "i2c") and self._kb.i2c is not None:
            self._i2c = self._kb.i2c
        elif self._hw is not None and hasattr(self._hw, "i2c") and self._hw.i2c is not None:
            self._i2c = self._hw.i2c
        elif machine is not None:
            try:
                self._i2c = machine.I2C(
                    I2C_SB_BUS,
                    sda=machine.Pin(PIN_SB_SDA),
                    scl=machine.Pin(PIN_SB_SCL),
                    freq=I2C_SB_FREQ,
                )
            except Exception:
                self._i2c = None

        # Register non-blocking sys.stdin poller for terminal / keyboard stream input
        if _select_mod is not None and hasattr(_select_mod, "poll"):
            try:
                import sys
                p = _select_mod.poll()
                p.register(sys.stdin, _select_mod.POLLIN)
                self._stdin_poll = p
            except Exception:
                self._stdin_poll = None

        self.recover_refresh()
        import sys as _sys
        _m = _sys.modules.get("main")
        if not (_m is not None and getattr(_m, "_boot_splash_active", False)):
            self.set_lut(self._lut)
        self.set_backlight(self._backlight_pct)
        self.set_kb_backlight(self._kb_backlight_pct)
        self.clear_input()
        self.init_uart_bridge(rebind=False)
        self.initialized = True
        return True

    def restore_state(self):
        """Restore default LUT, display auto-refresh, close aux UART, and clear input after sandbox exit."""
        self.close_aux_uart()
        super().restore_state()
        self.set_lut(self._lut)

    # --- Display Primitives & Blitting ---

    def set_lut(self, lut):
        """
        Update the 16-entry RGB565 LUT in-place without stopping/restarting Core 1
        auto-refresh (repeated stopRefresh/recoverRefresh calls wedge Core 1 on RP2350).
        """
        if lut is not None and len(lut) >= 16:
            for i in range(16):
                self._lut[i] = lut[i]
        if self._hw is not None and hasattr(self._hw, "picocalcdisplay"):
            try:
                self._hw.picocalcdisplay.setLUT(self._lut)
            except Exception:
                pass

    def reset_default_lut(self):
        """Restore factory 16-entry RGB565 LUT & native font (used by BSOD and Safe Recovery Mode)."""
        self._font_name = "default"
        self._font_mv = None
        self.set_lut(_build_default_lut())

    def stop_refresh(self):
        if self._disp is not None and hasattr(self._disp, "stopRefresh"):
            if self._refresh_active:
                try:
                    self._disp.stopRefresh()
                except Exception:
                    pass
                self._refresh_active = False
                import sys as _sys
                _sys.modules["__pinhos_disp_stopped__"] = True

    def recover_refresh(self, force=False):
        if self._disp is not None and hasattr(self._disp, "recoverRefresh"):
            import sys as _sys
            stopped = bool(_sys.modules.get("__pinhos_disp_stopped__"))
            if force or not self._refresh_active or stopped:
                try:
                    self._disp.recoverRefresh()
                except Exception:
                    pass
                self._refresh_active = True
                _sys.modules.pop("__pinhos_disp_stopped__", None)

    def fill(self, color=0):
        if self._disp is not None:
            self._disp.fill(color)
        elif self._fb is not None:
            self._fb.fill(color & 0x0F)

    def fill_rect(self, x, y, w, h, color):
        if self._disp is not None:
            self._disp.fill_rect(int(x), int(y), int(w), int(h), color)
        elif self._fb is not None:
            self._fb.fill_rect(int(x), int(y), int(w), int(h), color & 0x0F)

    def rect(self, x, y, w, h, color):
        if self._disp is not None:
            self._disp.rect(int(x), int(y), int(w), int(h), color)
        elif self._fb is not None:
            self._fb.rect(int(x), int(y), int(w), int(h), color & 0x0F)

    def hline(self, x, y, w, color):
        if self._disp is not None and hasattr(self._disp, "hline"):
            self._disp.hline(int(x), int(y), int(w), color)
        elif self._fb is not None:
            self._fb.hline(int(x), int(y), int(w), color & 0x0F)
        else:
            self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        if self._disp is not None and hasattr(self._disp, "vline"):
            self._disp.vline(int(x), int(y), int(h), color)
        elif self._fb is not None:
            self._fb.vline(int(x), int(y), int(h), color & 0x0F)
        else:
            self.fill_rect(x, y, 1, h, color)

    def line(self, x0, y0, x1, y1, color):
        if self._disp is not None and hasattr(self._disp, "line"):
            self._disp.line(int(x0), int(y0), int(x1), int(y1), color)
        elif self._fb is not None:
            self._fb.line(int(x0), int(y0), int(x1), int(y1), color & 0x0F)
        else:
            super().line(int(x0), int(y0), int(x1), int(y1), color)

    def pixel(self, x, y, color):
        if self._disp is not None and hasattr(self._disp, "pixel"):
            self._disp.pixel(int(x), int(y), color)
        elif self._fb is not None:
            self._fb.pixel(int(x), int(y), color & 0x0F)
        else:
            self.fill_rect(x, y, 1, 1, color)

    def text(self, s, x, y, color=15):
        text_str = str(s)
        if self._font_mv is not None and self._font_name != "default":
            from ui.fonts import draw_text_6x8
            if self._disp is not None:
                draw_text_6x8(self._disp, text_str, int(x), int(y), int(color), self._font_mv)
            elif self._fb is not None:
                draw_text_6x8(self._fb, text_str, int(x), int(y), int(color) & 0x0F, self._font_mv)
            return
        if self._disp is not None:
            self._disp.text(text_str, int(x), int(y), color)
        elif self._fb is not None:
            self._fb.text(text_str, int(x), int(y), color & 0x0F)

    def blit(self, buf, x, y, w, h, fmt="RGB565"):
        """Blit a raw buffer or FrameBuffer region onto the 320x320 display."""
        if self._disp is not None:
            if hasattr(self._disp, "blit") and framebuf is not None:
                try:
                    if isinstance(buf, framebuf.FrameBuffer):
                        self._disp.blit(buf, int(x), int(y))
                        return True
                    mode = framebuf.GS4_HMSB if fmt == "GS4_HMSB" else framebuf.RGB565
                    fb_src = framebuf.FrameBuffer(buf, int(w), int(h), mode)
                    self._disp.blit(fb_src, int(x), int(y))
                    return True
                except Exception:
                    pass
            # Fallback scanline fill if raw buffer passed
            self.fill_rect(int(x), int(y), int(w), int(h), 0)
            return True
        elif self._fb is not None and framebuf is not None:
            try:
                if isinstance(buf, framebuf.FrameBuffer):
                    self._fb.blit(buf, int(x), int(y))
                else:
                    fb_src = framebuf.FrameBuffer(buf, int(w), int(h), framebuf.GS4_HMSB)
                    self._fb.blit(fb_src, int(x), int(y))
                return True
            except Exception:
                return False
        return False

    def show(self):
        if self._disp is not None and hasattr(self._disp, "show"):
            try:
                self._disp.show()
            except Exception:
                pass

    # --- Keyboard Matrix Scan & Modifier Decoding ---

    def _decode_raw_key(self, raw_bytes):
        """Decode raw STM32 southbridge (0x1F) / VT100 byte sequence into (key_name, modifiers)."""
        if not raw_bytes:
            return (None, MOD_NONE)

        mods = self._modifiers
        b = bytes(raw_bytes)

        # Unwrap 2-byte STM32 FIFO [state, keycode] packet if passed directly
        if len(b) == 2 and b[0] in (1, 2, 3) and b[0] != 0x1B:
            if b[0] == 3 or b[1] == 0:
                return (None, mods)
            b = bytes([b[1]])

        # Standalone STM32 modifier keycodes (0xA1/0xA2 Shift, 0xA3/0xA5 Ctrl on PicoCalc, 0xA4 Alt)
        if len(b) == 1 and b[0] in (0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            if b[0] in (0xA1, 0xA2):
                mods |= MOD_SHIFT
            elif b[0] in (0xA3, 0xA5):
                mods |= MOD_CTRL
            elif b[0] == 0xA4:
                mods |= MOD_ALT
            self._modifiers = mods
            return (None, mods)

        # Function keys F1..F5 & PicoCalc Shifted F6..F10 (STM32 0x81..0x8A + VT100)
        if b.startswith(b"\x1b[1;2P") or b.startswith(b"\x1b[11;2~") or b.startswith(b"\x1b[17;2~"):
            return ("F6", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[1;2Q") or b.startswith(b"\x1b[12;2~") or b.startswith(b"\x1b[18;2~"):
            return ("F7", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[1;2R") or b.startswith(b"\x1b[13;2~") or b.startswith(b"\x1b[19;2~"):
            return ("F8", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[1;2S") or b.startswith(b"\x1b[14;2~") or b.startswith(b"\x1b[20;2~"):
            return ("F9", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[15;2~") or b.startswith(b"\x1b[21;2~"):
            return ("F10", mods | MOD_SHIFT)

        if b"\x81" in b or b.startswith(b"\x1bOP") or b.startswith(b"\x1b[11~"):
            return ("F6", mods) if (mods & MOD_SHIFT) else ("F1", mods)
        if b"\x82" in b or b.startswith(b"\x1bOQ") or b.startswith(b"\x1b[12~"):
            return ("F7", mods) if (mods & MOD_SHIFT) else ("F2", mods)
        if b"\x83" in b or b.startswith(b"\x1bOR") or b.startswith(b"\x1b[13~"):
            return ("F8", mods) if (mods & MOD_SHIFT) else ("F3", mods)
        if b"\x84" in b or b.startswith(b"\x1bOS") or b.startswith(b"\x1b[14~"):
            return ("F9", mods) if (mods & MOD_SHIFT) else ("F4", mods)
        if b"\x85" in b or b.startswith(b"\x1b[15~"):
            return ("F10", mods) if (mods & MOD_SHIFT) else ("F5", mods)
        if b"\x86" in b:
            return ("F6", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[17~"):
            return ("F6", mods)
        if b"\x87" in b:
            return ("F7", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[18~"):
            return ("F7", mods)
        if b"\x88" in b:
            return ("F8", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[19~"):
            return ("F8", mods)
        if b"\x89" in b:
            return ("F9", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[20~"):
            return ("F9", mods)
        if b"\x8a" in b or b"\x90" in b:
            return ("F10", mods | MOD_SHIFT)
        if b.startswith(b"\x1b[21~"):
            return ("F10", mods)

        # Directional D-Pad / Arrow / Page keys
        if b.startswith(b"\x1b[A") or b in (b"\xb5", b"\xd6") or b.startswith(b"\x1b[5~"):
            return ("UP", mods)
        if b.startswith(b"\x1b[B") or b in (b"\xb6", b"\xd7") or b.startswith(b"\x1b[6~"):
            return ("DOWN", mods)
        if b.startswith(b"\x1b[D") or b in (b"\xb4", b"\xd2") or b.startswith(b"\x1b[H"):
            return ("LEFT", mods)
        if b.startswith(b"\x1b[C") or b in (b"\xb7", b"\xd5") or b.startswith(b"\x1b[F"):
            return ("RIGHT", mods)

        # Navigation & Control keys (0xB1 = PicoCalc physical ESC, 0xD4 = PicoCalc physical DEL)
        if b in (b"\r", b"\n"):
            return ("ENTER", mods)
        if b == b" ":
            return ("SPACE", mods)
        if b in (b"\x08", b"\x7f", b"\xd4") or b.startswith(b"\x1b[3~"):
            return ("BACKSPACE", mods)
        if b == b"\t":
            return ("TAB", mods)
        if b in (b"\x1b", b"\x1b\x1b", b"\xb1"):
            return ("ESC", mods)
        if b in (b"\xb0", b"\xd0", b"\x91"):
            return ("POWER", mods)

        # Alt + Key (ESC prefix followed by printable char)
        if len(b) == 2 and b[0] == 0x1B and 32 <= b[1] <= 126:
            mods |= MOD_ALT
            ch = chr(b[1])
            if "A" <= ch <= "Z":
                mods |= MOD_SHIFT
            return (ch, mods)

        # Ctrl + A..Z (0x01..0x1A, excluding Backspace=0x08, Tab=0x09, LF=0x0A, CR=0x0D)
        if len(b) == 1 and 1 <= b[0] <= 26 and b[0] not in (8, 9, 10, 13):
            mods |= MOD_CTRL
            return (chr(64 + b[0]), mods)

        # Standard printable ASCII characters (32..126)
        if len(b) == 1 and 32 <= b[0] <= 126:
            ch = chr(b[0])
            if "A" <= ch <= "Z" or ch in '~!@#$%^&*()_+{}|:"<>?':
                mods |= MOD_SHIFT
            return (ch, mods)

        try:
            s = b.decode("utf-8", "ignore")
            if s and 32 <= ord(s[0]) <= 126:
                ch = s[0]
                if "A" <= ch <= "Z" or ch in '~!@#$%^&*()_+{}|:"<>?':
                    mods |= MOD_SHIFT
                return (ch, mods)
        except Exception:
            pass

        return (None, mods)

    def _poll_i2c_keyboard(self):
        """
        Poll the ClockworkPi PicoCalc STM32 keyboard controller (I2C1 addr 0x1F).
        Prefers picocalc.keyboard.keyEvent() (10kHz I2C + 2-byte reg 0x04 & 0x1F mask),
        falling back to direct I2C reg 0x04/0x09 reads when picocalc.keyboard is absent.
        """
        for _ in range(4):
            state = 0
            code = 0
            if self._kb is not None and hasattr(self._kb, "keyEvent"):
                try:
                    ev = self._kb.keyEvent()
                    if not ev or len(ev) < 2:
                        return None
                    state = ev[0]
                    code = ev[1]
                except Exception:
                    return None
            else:
                i2c = self._i2c
                if i2c is None:
                    return None
                try:
                    i2c.writeto(SB_I2C_ADDR, b"\x04")
                    cnt_buf = i2c.readfrom(SB_I2C_ADDR, 2)
                    if not cnt_buf or (cnt_buf[0] & 0x1F) == 0:
                        return None
                    i2c.writeto(SB_I2C_ADDR, b"\x09")
                    data = i2c.readfrom(SB_I2C_ADDR, 2)
                    if not data or len(data) < 2:
                        return None
                    state = data[0]
                    code = data[1]
                except Exception:
                    return None

            # Empty or idle FIFO read
            if state in (0, 0xFF) or code in (0, 0xFF):
                return None

            # Key released (state == 3): clear modifier if modifier key, else discard & check next FIFO slot
            # PicoCalc STM32 scancodes: 0xA1=ALT, 0xA2=LSHIFT, 0xA3=RSHIFT, 0xA4=SYM, 0xA5=CTRL
            if state == 3:
                if code in (0xA2, 0xA3):
                    self._modifiers &= ~MOD_SHIFT
                elif code == 0xA5:
                    self._modifiers &= ~MOD_CTRL
                elif code in (0xA1, 0xA4):
                    self._modifiers &= ~MOD_ALT
                continue

            # Key pressed (state == 1) or held (state == 2)
            if state in (1, 2):
                if code in (0xA2, 0xA3):
                    self._modifiers |= MOD_SHIFT
                    continue
                if code == 0xA5:
                    self._modifiers |= MOD_CTRL
                    continue
                if code in (0xA1, 0xA4):
                    self._modifiers |= MOD_ALT
                    continue
                return bytes([code])

            return None
        return None

    def _poll_stdin_nonblocking(self):
        """Check sys.stdin non-blockingly for single keys or ANSI escape sequences."""
        if self._stdin_poll is None:
            return None
        try:
            import sys
            if not self._stdin_poll.poll(0):
                return None
            ch = sys.stdin.read(1)
            if not ch:
                return None
            b = ch if isinstance(ch, (bytes, bytearray)) else ch.encode("utf-8")
            if b == b"\x03":
                raise KeyboardInterrupt
            # Assemble multi-byte ANSI escape sequences (\x1b[A, \x1bOP, etc.)
            if b == b"\x1b":
                seq = bytearray(b)
                for _ in range(5):
                    if self._stdin_poll.poll(12):
                        nxt = sys.stdin.read(1)
                        if not nxt:
                            break
                        nb = nxt if isinstance(nxt, (bytes, bytearray)) else nxt.encode("utf-8")
                        seq.extend(nb)
                        last_c = seq[-1]
                        if (65 <= last_c <= 90) or (97 <= last_c <= 122) or last_c == 126:
                            break
                    else:
                        break
                return bytes(seq)
            return bytes(b)
        except KeyboardInterrupt:
            raise
        except Exception:
            return None

    def poll_input(self):
        """
        Poll PicoCalc keyboard input from both the onboard STM32 I2C keyboard controller
        (0x1F) and sys.stdin / picocalc.keyboard so physical keys work even when UART(0)
        is attached to os.dupterm(..., 0).
        """
        count = 0
        raw = None

        # 0. Non-blocking COM4 (UART0) Ctrl-C interrupt check (only when LNK serial link is enabled):
        # When LNK is OFF, silently drain/discard stray RX bytes so host Ctrl+C cannot interrupt UI.
        if self._uart is not None:
            try:
                if self._serial_link_enabled:
                    if self._uart.any():
                        ch = self._uart.read(1)
                        if ch and (b"\x03" in ch):
                            raise KeyboardInterrupt
                        if hasattr(os, "dupterm_notify"):
                            os.dupterm_notify(self._uart)
                else:
                    n_rx = self._uart.any()
                    if n_rx:
                        self._uart.read(n_rx)
            except KeyboardInterrupt:
                raise
            except Exception:
                pass

        # 1. Direct STM32 I2C keyboard controller (via picocalc.keyboard.keyEvent() / 0x1F)
        raw = self._poll_i2c_keyboard()

        # 2. Only fall back to sys.stdin polling when no physical keyboard/I2C bus is present
        # (avoids sys.stdin.read(1) blocking ui_loop() on RP2350 when UART0 dupterm is active)
        if raw is None and self._kb is None and self._i2c is None:
            raw = self._poll_stdin_nonblocking()

        if raw:
            key_name, mods = self._decode_raw_key(raw)
            self._modifiers = mods
            # Global screenshot shortcut CTRL+P: capture clean 4-bit BMP FIRST in the HAL,
            # beep, and also pass the CTRL+P key event through so the active view/tool can
            # show the "SCREENSHOT SAVED" confirmation toast + FooterBar status immediately.
            if key_name is not None and (mods & MOD_CTRL) and str(key_name).upper() == "P":
                try:
                    self.screenshot()
                except Exception:
                    pass
            if key_name is not None:
                self.push_event({
                    "type": "key",
                    "key": key_name,
                    "raw": raw,
                    "modifiers": mods,
                })
                count += 1
        return count

    def poll_key(self):
        """Non-blocking key poll returning the next key string or None (also feeds WDT if active)."""
        try:
            _w = sys.modules.get("__pinhos_wdt__")
            if _w is not None:
                _w.feed()
        except Exception:
            pass
        return self.read_key()

    # --- Screenshot (4bpp indexed BMP streamed to SD, zero extra SRAM) ---

    SCREENSHOT_DIR = "/sd/pinhos/screenshots"

    def get_framebuffer(self):
        """Return a zero-copy memoryview of the live 4bpp GS4_HMSB framebuffer (or None)."""
        try:
            if self._disp is not None:
                return memoryview(self._disp)
            if self._fb_buf is not None:
                return memoryview(self._fb_buf)
        except Exception:
            pass
        return None

    def _screenshot_path(self):
        try:
            os.mkdir("/sd/pinhos")
        except Exception:
            pass
        try:
            os.mkdir(self.SCREENSHOT_DIR)
        except Exception:
            pass
        d = self.get_rtc_datetime()
        base = "{}/shot_{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}".format(
            self.SCREENSHOT_DIR, d[0], d[1], d[2], d[4], d[5], d[6]
        )
        path = base + ".bmp"
        n = 1
        while True:
            try:
                os.stat(path)
            except OSError:
                return path
            path = "{}_{}.bmp".format(base, n)
            n += 1

    def prune_screenshots(self, keep=5):
        """Keep only the newest `keep` shot_*.bmp files on SD (preserves last.bmp) (#19)."""
        try:
            names = [n for n in os.listdir(self.SCREENSHOT_DIR) if n.startswith("shot_") and n.endswith(".bmp")]
            if len(names) <= int(keep):
                return 0
            names.sort()
            removed = 0
            for old in names[:-int(keep)]:
                try:
                    os.remove(self.SCREENSHOT_DIR + "/" + old)
                    removed += 1
                except OSError:
                    pass
            return removed
        except Exception:
            return 0

    def screenshot_iter(self, path=None, step_rows=32):
        """
        Cooperative generator yielding every `step_rows` rows while streaming a 320x320
        4-bit indexed BMP to SD (~200 B SRAM). Final yielded value is saved path or None (#19).
        """
        import struct
        mv = self.get_framebuffer()
        if mv is None:
            yield None
            return
        w, h = self.display_width, self.display_height
        row = w // 2
        if len(mv) < row * h:
            yield None
            return
        if path is None:
            path = self._screenshot_path()
        try:
            os.mkdir("/sd/pinhos")
        except Exception:
            pass
        try:
            os.mkdir(self.SCREENSHOT_DIR)
        except Exception:
            pass
        try:
            data_sz = row * h
            f = open(path, "wb")
            try:
                f.write(struct.pack("<2sIHHI", b"BM", 14 + 40 + 64 + data_sz, 0, 0, 14 + 40 + 64))
                f.write(struct.pack("<IiiHHIIiiII", 40, w, h, 1, 4, 0, data_sz, 2835, 2835, 16, 16))
                pal = bytearray(64)
                for i in range(16):
                    e = self._lut[i]
                    v = ((e & 0xFF) << 8) | (e >> 8)
                    r5 = (v >> 11) & 31
                    g6 = (v >> 5) & 63
                    b5 = v & 31
                    pal[i * 4] = (b5 << 3) | (b5 >> 2)
                    pal[i * 4 + 1] = (g6 << 2) | (g6 >> 4)
                    pal[i * 4 + 2] = (r5 << 3) | (r5 >> 2)
                f.write(pal)
                cnt = 0
                sr = max(8, int(step_rows))
                for y in range(h - 1, -1, -1):
                    f.write(mv[y * row:(y + 1) * row])
                    cnt += 1
                    if cnt >= sr:
                        cnt = 0
                        yield False
            finally:
                f.close()
        except Exception:
            yield None
            return
        self.last_screenshot = path
        self.pending_screenshot = path
        if path.rpartition("/")[2].startswith("shot_"):
            self.prune_screenshots(keep=5)
        self.beep(1800, 25)
        self.beep(2400, 25)
        try:
            self.serial_print("[SCREENSHOT]", path)
        except Exception:
            pass
        yield path

    def screenshot(self, path=None):
        """
        Save the current screen as a 320x320 4-bit indexed BMP (palette = live theme LUT).
        Streams row-by-row from the framebuffer (bottom-up), so SRAM cost is ~200 bytes.
        Returns the saved path, or None on failure.
        """
        res = None
        for step in self.screenshot_iter(path=path, step_rows=64):
            res = step
        return res if isinstance(res, str) else None

    def pop_pending_screenshot(self):
        p = self.pending_screenshot
        self.pending_screenshot = None
        return p

    # --- SPI microSD Card Mount / Unmount with Retry Logic ---

    def is_sd_mounted(self, mount_point="/sd"):
        try:
            entries = os.listdir("/")
            mp_name = mount_point.strip("/")
            if mp_name not in entries:
                return False
            os.listdir(mount_point)
            self._sd_mounted = True
            return True
        except Exception:
            self._sd_mounted = False
            return False

    def _boost_sd_spi(self, baudrate=SD_BAUDRATE, mount_point="/sd"):
        """
        Safely boost SPI0 clock to 25 MHz (SD SPI spec max) after mount.
        Auto-falls back to 12 MHz if the card fails a quick directory read.
        """
        if self._sd_spi_boosted:
            return True
        spi_obj = None
        if self._hw is not None:
            for attr in ("sd", "sdcard"):
                obj = getattr(self._hw, attr, None)
                if obj is None:
                    continue
                for sub in ("spi", "_spi"):
                    cand = getattr(obj, sub, None)
                    if cand is not None and hasattr(cand, "init"):
                        spi_obj = cand
                        break
                if spi_obj is None:
                    inner = getattr(obj, "sd", None) or getattr(obj, "sdcard", None)
                    if inner is not None:
                        cand = getattr(inner, "spi", None) or getattr(inner, "_spi", None)
                        if cand is not None and hasattr(cand, "init"):
                            spi_obj = cand
                if spi_obj is not None:
                    break
        try:
            if spi_obj is not None:
                spi_obj.init(baudrate=int(baudrate))
            elif machine is not None:
                machine.SPI(
                    SPI_SD_BUS,
                    baudrate=int(baudrate),
                    polarity=0,
                    phase=0,
                    bits=8,
                    firstbit=machine.SPI.MSB,
                    sck=machine.Pin(PIN_SD_SCK),
                    mosi=machine.Pin(PIN_SD_MOSI),
                    miso=machine.Pin(PIN_SD_MISO),
                )
            else:
                return False
            # Verify card still responds cleanly at boosted clock
            os.listdir(mount_point)
            self._sd_spi_boosted = True
            return True
        except Exception:
            # Fallback to safe 12 MHz if card/wiring dislikes 25 MHz
            try:
                if spi_obj is not None:
                    spi_obj.init(baudrate=int(SD_BAUDRATE_FALLBACK))
                elif machine is not None:
                    machine.SPI(
                        SPI_SD_BUS,
                        baudrate=int(SD_BAUDRATE_FALLBACK),
                        polarity=0,
                        phase=0,
                        bits=8,
                        firstbit=machine.SPI.MSB,
                        sck=machine.Pin(PIN_SD_SCK),
                        mosi=machine.Pin(PIN_SD_MOSI),
                        miso=machine.Pin(PIN_SD_MISO),
                    )
            except Exception:
                pass
            return False

    def mount_sd(self, mount_point="/sd", retries=3):
        """Mount the PicoCalc SPI0 microSD card with automatic retry backoff."""
        self._sd_mount_point = mount_point
        if self.is_sd_mounted(mount_point):
            self._boost_sd_spi(SD_BAUDRATE, mount_point)
            return True

        tries = max(1, int(retries))
        for attempt in range(tries):
            try:
                # 1. Try native picocalc.sd / picocalc.sdcard mount helper
                if self._hw is not None:
                    sd_obj = getattr(self._hw, "sd", None) or getattr(self._hw, "sdcard", None)
                    if sd_obj is not None and hasattr(sd_obj, "mount"):
                        sd_obj.mount()
                        if self.is_sd_mounted(mount_point):
                            self._boost_sd_spi(SD_BAUDRATE, mount_point)
                            return True
                # 2. Try standard machine.SDCard / sdcard driver on SPI0 pins
                if machine is not None:
                    try:
                        import sdcard
                        spi = machine.SPI(
                            SPI_SD_BUS,
                            baudrate=SD_BAUDRATE,
                            sck=machine.Pin(PIN_SD_SCK),
                            mosi=machine.Pin(PIN_SD_MOSI),
                            miso=machine.Pin(PIN_SD_MISO),
                        )
                        sd = sdcard.SDCard(spi, machine.Pin(PIN_SD_CS, machine.Pin.OUT))
                        os.mount(sd, mount_point)
                        if self.is_sd_mounted(mount_point):
                            self._sd_spi_boosted = True
                            return True
                    except Exception:
                        pass
            except Exception:
                pass

            if attempt < tries - 1:
                try:
                    time.sleep_ms(100 * (attempt + 1))
                except Exception:
                    time.sleep(0.1)

        if self.is_sd_mounted(mount_point):
            self._boost_sd_spi(SD_BAUDRATE, mount_point)
            return True
        return False

    def unmount_sd(self, mount_point="/sd"):
        if not self.is_sd_mounted(mount_point):
            return True
        try:
            os.umount(mount_point)
            self._sd_mounted = False
            self._sd_spi_boosted = False
            return True
        except Exception:
            return False

    # --- Battery Voltage / Percentage / Charging Telemetry ---

    def get_battery(self):
        """
        Read battery telemetry from the STM32 Southbridge PMU register (0x0B).
        Returns: {"percent": int(0..100), "voltage_mv": int, "charging": bool, "present": bool}
        """
        now_ms = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
        diff = (
            time.ticks_diff(now_ms, self._last_bat_ms)
            if hasattr(time, "ticks_diff")
            else (now_ms - self._last_bat_ms)
        )
        if self._last_bat_ms != 0 and diff < 5000:
            return dict(self._bat_cache)

        raw = None
        if self._kb is not None and hasattr(self._kb, "battery"):
            try:
                raw = self._kb.battery()
            except Exception:
                raw = None
        elif self._i2c is not None:
            try:
                raw = self._i2c.readfrom_mem(SB_I2C_ADDR, REG_SB_BATTERY, 2)
            except Exception:
                raw = None

        pct = self._bat_cache["percent"]
        charging = self._bat_cache["charging"]
        voltage_mv = self._bat_cache["voltage_mv"]

        if isinstance(raw, (bytes, bytearray)) and len(raw) >= 2:
            val = raw[1] & 0x7F
            charging = bool(raw[1] & 0x80)
            if 0 <= val <= 100:
                pct = val
            # Estimate LiPo cell voltage (3300mV empty .. 4200mV full)
            voltage_mv = 3300 + int((pct * 900) // 100)
        elif isinstance(raw, int):
            pct = max(0, min(100, raw & 0x7F))
            charging = bool(raw & 0x80)
            voltage_mv = 3300 + int((pct * 900) // 100)

        self._bat_cache = {
            "percent": pct,
            "voltage_mv": voltage_mv,
            "charging": charging,
            "present": True,
        }
        self._last_bat_ms = now_ms
        return dict(self._bat_cache)

    # --- Screen & Keyboard Backlight PWM (0..100%) ---

    def _read_hw_backlight(self):
        """Read raw STM32 LCD backlight register (0x05) via kb.read_reg16 or I2C (0..255 or 0..100)."""
        if self._kb is not None and hasattr(self._kb, "read_reg16"):
            try:
                raw = self._kb.read_reg16(REG_SB_LCD_BKL)
                if isinstance(raw, (bytes, bytearray)) and len(raw) >= 2:
                    return int(raw[1])
            except Exception:
                pass
        if self._i2c is not None:
            try:
                self._i2c.writeto(SB_I2C_ADDR, bytes([REG_SB_LCD_BKL]))
                raw = self._i2c.readfrom(SB_I2C_ADDR, 2)
                if isinstance(raw, (bytes, bytearray)) and len(raw) >= 2:
                    return int(raw[1])
            except Exception:
                pass
        return None

    def set_backlight(self, percent):
        """
        Set LCD backlight brightness (0..100%).
        Caches requested 0..100% value locally so get_backlight() is deterministic
        even when the STM32 I2C register (0x1F, reg 0x05) is quantized or write-only.
        """
        pct = max(0, min(100, int(round(percent))))
        self._backlight_pct = pct
        self._last_bl_set_ms = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
        ok = False
        if self._kb is not None and hasattr(self._kb, "setBacklight"):
            try:
                self._kb.setBacklight(pct)
                ok = True
            except Exception:
                pass
        if (not ok) and self._i2c is not None:
            try:
                self._i2c.writeto_mem(SB_I2C_ADDR, REG_SB_LCD_BKL, bytes([pct]))
                ok = True
            except Exception:
                pass
        hw = self._read_hw_backlight()
        if hw is not None:
            self._last_hw_bl = hw
            if pct >= 50:
                self._bl_scale = 255 if hw > 100 else 100
        return True

    def get_backlight(self):
        """Return active LCD backlight percentage (0..100%), syncing live STM32 hardware shortcut changes (#82)."""
        now_ms = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
        since_set = time.ticks_diff(now_ms, self._last_bl_set_ms) if hasattr(time, "ticks_diff") else (now_ms - self._last_bl_set_ms)
        since_poll = time.ticks_diff(now_ms, self._last_bl_poll_ms) if hasattr(time, "ticks_diff") else (now_ms - self._last_bl_poll_ms)
        if (self._last_bl_set_ms == 0 or since_set > 1500) and (self._last_bl_poll_ms == 0 or since_poll > 800):
            self._last_bl_poll_ms = now_ms
            hw = self._read_hw_backlight()
            if hw is not None:
                if hw > 100:
                    self._bl_scale = 255
                if self._last_hw_bl is not None and hw != self._last_hw_bl:
                    self._backlight_pct = max(0, min(100, int(round((hw * 100.0) / max(1, self._bl_scale)))))
                self._last_hw_bl = hw
        return int(self._backlight_pct)

    def set_kb_backlight(self, percent):
        """
        Set keyboard backlight brightness (0..100%).
        Caches requested 0..100% value locally for deterministic readback.
        """
        pct = max(0, min(100, int(round(percent))))
        self._kb_backlight_pct = pct
        if self._kb is not None and hasattr(self._kb, "setBacklight_keyboard"):
            try:
                self._kb.setBacklight_keyboard(pct)
                return True
            except Exception:
                pass
        if self._i2c is not None:
            try:
                self._i2c.writeto_mem(SB_I2C_ADDR, REG_SB_KB_BKL, bytes([pct]))
                return True
            except Exception:
                pass
        return True

    def get_kb_backlight(self):
        """Return active keyboard backlight percentage (0..100%)."""
        return int(self._kb_backlight_pct)

    # --- Audio / PWM Buzzer ---

    def beep(self, freq=1200, duration_ms=18, volume=50):
        if not self.config.get("sound", True) or volume <= 0 or self.audio_playing():
            return False
        if machine is None:
            return False
        try:
            pwm = machine.PWM(machine.Pin(PIN_AUDIO_L))
            pwm.freq(max(80, min(8000, int(freq))))
            duty = int((max(1, min(100, int(volume))) * 32768) // 100)
            pwm.duty_u16(duty)
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(int(duration_ms))
            else:
                time.sleep(duration_ms / 1000.0)
            pwm.duty_u16(0)
            pwm.deinit()
            return True
        except Exception:
            return False

    def play_audio(self, path):
        """
        Start cooperative non-blocking PCM WAV playback over PicoCalc PWM (GP26 L / GP27 R @ 62.5 kHz).
        Parses RIFF/WAVE headers (8/16-bit, mono/stereo, 8000-22050 Hz), skips LIST/INFO metadata
        subchunks cleanly, and lazily allocates one reusable 512 B buffer (zero per-chunk allocation).
        """
        import struct
        self.stop_audio()
        self._aud_err = ""
        f = None
        try:
            f = open(path, "rb")
            hdr = f.read(12)
            if len(hdr) < 12 or hdr[0:4] != b"RIFF" or hdr[8:12] != b"WAVE":
                self._aud_err = "Not a RIFF/WAVE file"
                f.close()
                return False
            fmt_ok = False
            ch, rate, bits, data_sz = 1, 8000, 8, 0
            while True:
                chdr = f.read(8)
                if len(chdr) < 8:
                    break
                cid, csz = struct.unpack("<4sI", chdr)
                if cid == b"fmt ":
                    fb = f.read(min(16, csz))
                    if len(fb) < 16:
                        self._aud_err = "Truncated fmt chunk"
                        f.close()
                        return False
                    afmt, ch, rate, _, _, bits = struct.unpack("<HHIIHH", fb)
                    if csz > 16:
                        f.seek(csz - 16, 1)
                    if csz & 1:
                        f.seek(1, 1)
                    if afmt != 1 or ch not in (1, 2) or bits not in (8, 16) or rate < 8000 or rate > 22050:
                        self._aud_err = "Need PCM 8/16b 8-22kHz"
                        f.close()
                        return False
                    fmt_ok = True
                elif cid == b"data":
                    data_sz = csz
                    break
                else:
                    # Skip LIST / INFO / JUNK / fact / bext metadata subchunks cleanly
                    f.seek(csz + (csz & 1), 1)
            if (not fmt_ok) or data_sz <= 0:
                self._aud_err = "Missing PCM data chunk"
                f.close()
                return False
            if self._aud_buf is None:
                self._aud_buf = bytearray(4096)
                self._aud_mv = memoryview(self._aud_buf)
            self._aud_top = 0
            if machine is not None:
                self._aud_pwm_l = machine.PWM(machine.Pin(PIN_AUDIO_L))
                self._aud_pwm_r = machine.PWM(machine.Pin(PIN_AUDIO_R))
                self._aud_pwm_l.freq(62500)
                self._aud_pwm_r.freq(62500)
                self._aud_pwm_l.duty_u16(32768)
                self._aud_pwm_r.duty_u16(32768)
                try:
                    t = int(machine.mem32[_RP2350_PWM5_TOP]) & 0xFFFF
                    if 100 <= t <= 65535:
                        self._aud_top = t
                except Exception:
                    self._aud_top = 0
            self._aud_f = f
            self._aud_rate = rate
            self._aud_ch = ch
            self._aud_bits = bits
            self._aud_total = data_sz
            self._aud_rem = data_sz
            self._aud_bps = max(1, rate * ch * (bits // 8))
            self._aud_us = max(40, 1000000 // rate)
            # Lazy-load native ARM Thumb-2 @viper audio helpers (0 B SRAM when idle)
            self._aud_pack = None
            self._aud_feed = None
            try:
                from boards._audio_viper import feed_pwm, pack_pwm
                self._aud_pack = pack_pwm
                self._aud_feed = feed_pwm
            except Exception:
                pass
            # Engage RP2350 hardware rp2.DMA double-buffering (zero breaks, 1.000x exact pitch)
            if machine is not None and self._aud_top > 0 and self._aud_pack is not None:
                try:
                    import rp2
                    if hasattr(rp2, "DMA"):
                        # Configure DMA pacing TIMER0: sys_clk * 1 / y = sample rate (TREQ_SEL=0x3B)
                        div_y = max(1, min(65535, int(machine.freq()) // rate))
                        machine.mem32[_RP2350_DMA_TMR0] = (1 << 16) | div_y
                        self._aud_dma_bufs = (array.array("I", bytearray(8192)), array.array("I", bytearray(8192)))
                        self._aud_dma = rp2.DMA()
                        self._aud_ctrl = self._aud_dma.pack_ctrl(
                            size=2, inc_read=True, inc_write=False, treq_sel=0x3B
                        )
                        self._aud_cur = 0
                        self._aud_next_cnt = 0
                        c0 = self._fill_dma_buf(0)
                        if c0 > 0:
                            self._aud_dma.config(
                                read=self._aud_dma_bufs[0],
                                write=_RP2350_PWM5_CC,
                                count=c0,
                                ctrl=self._aud_ctrl,
                                trigger=True,
                            )
                            self._aud_next_cnt = self._fill_dma_buf(1)
                except Exception:
                    if self._aud_dma is not None:
                        try:
                            self._aud_dma.active(0)
                            self._aud_dma.close()
                        except Exception:
                            pass
                    self._aud_dma = None
                    self._aud_dma_bufs = None
            return True
        except Exception as e:
            self._aud_err = str(e)[:32]
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass
            self.stop_audio()
            return False

    def _fill_dma_buf(self, slot):
        """Read next PCM chunk from SD and pack into 32-bit PWM5_CC words for DMA slot 0/1."""
        f = self._aud_f
        rem = self._aud_rem
        if f is None or rem <= 0 or self._aud_dma_bufs is None:
            return 0
        # Cap read bytes so packed sample count never exceeds 2048 words (8 KB slot)
        bps_frame = self._aud_ch * (self._aud_bits // 8)
        max_b = min(4096, 2048 * bps_frame)
        want = max_b if rem >= max_b else rem
        try:
            n = f.readinto(self._aud_mv[:want])
        except Exception:
            return 0
        if not n:
            self._aud_rem = 0
            return 0
        self._aud_rem = rem - n
        return int(self._aud_pack(self._aud_buf, self._aud_dma_bufs[slot], n, self._aud_bits, self._aud_ch, self._aud_top))

    def step_audio(self):
        """Feed one pre-allocated PCM chunk to GP26/GP27 PWM (non-blocking rp2.DMA double-buffer if active)."""
        if self._aud_dma is not None:
            dma = self._aud_dma
            if dma.active():
                if self._aud_next_cnt == 0 and self._aud_rem > 0:
                    self._aud_next_cnt = self._fill_dma_buf(1 - self._aud_cur)
                return True
            if self._aud_next_cnt > 0:
                self._aud_cur = 1 - self._aud_cur
                cnt = self._aud_next_cnt
                self._aud_next_cnt = 0
                dma.config(
                    read=self._aud_dma_bufs[self._aud_cur],
                    write=_RP2350_PWM5_CC,
                    count=cnt,
                    ctrl=self._aud_ctrl,
                    trigger=True,
                )
                if self._aud_rem > 0:
                    self._aud_next_cnt = self._fill_dma_buf(1 - self._aud_cur)
                return True
            self.stop_audio()
            return False

        f = self._aud_f
        rem = self._aud_rem
        if f is None or rem <= 0:
            if f is not None:
                self.stop_audio()
            return False
        mv = self._aud_mv
        want = 4096 if rem >= 4096 else rem
        try:
            n = f.readinto(mv[:want])
        except Exception:
            self.stop_audio()
            return False
        if not n:
            self.stop_audio()
            return False
        self._aud_rem = rem - n
        pl = self._aud_pwm_l
        pr = self._aud_pwm_r
        if pl is not None and pr is not None:
            if self._aud_feed is not None and self._aud_top > 0:
                self._aud_feed(self._aud_buf, n, self._aud_bits, self._aud_ch, self._aud_us, self._aud_top)
            else:
                # Minimal fallback if _audio_viper is unavailable
                step = self._aud_ch * (self._aud_bits // 8)
                i = 0
                lim = n - step + 1
                while i < lim:
                    d = (mv[i] << 8) if self._aud_bits == 8 else ((mv[i] | (mv[i + 1] << 8)) ^ 0x8000)
                    pl.duty_u16(d); pr.duty_u16(d)
                    i += step
        if self._aud_rem <= 0:
            self.stop_audio()
            return False
        return True

    def audio_playing(self):
        if self._aud_dma is not None:
            try:
                if self._aud_dma.active() or self._aud_next_cnt > 0:
                    return True
            except Exception:
                pass
        return bool(self._aud_f is not None and self._aud_rem > 0)

    def audio_status(self):
        playing = self.audio_playing()
        played = max(0, self._aud_total - self._aud_rem)
        bps = max(1, self._aud_bps)
        return {
            "playing": playing,
            "pos_s": played // bps,
            "dur_s": self._aud_total // bps,
            "rate": self._aud_rate,
            "ch": self._aud_ch,
            "bits": self._aud_bits,
            "error": self._aud_err,
        }

    def stop_audio(self):
        if self._aud_dma is not None:
            try:
                self._aud_dma.active(0)
                self._aud_dma.close()
            except Exception:
                pass
            self._aud_dma = None
        self._aud_dma_bufs = None
        self._aud_next_cnt = 0
        self._aud_pack = None
        self._aud_feed = None
        try:
            import sys as _sys
            _sys.modules.pop("boards._audio_viper", None)
        except Exception:
            pass
        if self._aud_f is not None:
            try:
                self._aud_f.close()
            except Exception:
                pass
            self._aud_f = None
        self._aud_rem = 0
        self._aud_buf = None
        self._aud_mv = None
        for attr in ("_aud_pwm_l", "_aud_pwm_r"):
            p = getattr(self, attr, None)
            if p is not None:
                try:
                    p.duty_u16(0)
                    p.deinit()
                except Exception:
                    pass
                setattr(self, attr, None)
        if machine is None:
            return
        for pin_id in (PIN_AUDIO_L, PIN_AUDIO_R):
            try:
                pwm = machine.PWM(machine.Pin(pin_id))
                pwm.duty_u16(0)
                pwm.deinit()
            except Exception:
                pass

    # --- Die Temperature & Serial Bridge ---

    def get_cpu_temp_c(self):
        if machine is None:
            return 28.0
        try:
            adc = machine.ADC(ADC_TEMP_CH)
            v = adc.read_u16() * (3.3 / 65535.0)
            return round(27.0 - (v - 0.706) / 0.001721, 1)
        except Exception:
            return 28.0

    # --- Read-only Bus Diagnostics (hwinfo / i2cscan) ---

    def i2c_scan(self):
        """
        Fast, STM32-safe read-only I2C probe on the 10 kHz southbridge bus.
        Avoids a full 119-address blind scan that can stall/timeout the 10 kHz STM32 I2C1 bus.
        """
        if self._i2c is None:
            return []
        found = []
        # Always verify STM32 southbridge (0x1F) + common field I2C expansion addresses
        for addr in (SB_I2C_ADDR, 0x20, 0x27, 0x3C, 0x3D, 0x48, 0x50, 0x57, 0x68, 0x76, 0x77):
            try:
                if addr == SB_I2C_ADDR and self._kb is not None:
                    found.append(addr)
                else:
                    self._i2c.writeto(addr, b"")
                    found.append(addr)
            except Exception:
                pass
        return sorted(found)

    def get_i2c_known(self):
        return {SB_I2C_ADDR: "STM32 southbridge (kbd/bat/bkl)"}

    def get_bus_info(self):
        return {
            "i2c": self._i2c is not None,
            "uart": self._uart is not None,
            "aux_uart": self._aux_uart is not None,
            "sd": bool(self.is_sd_mounted()),
        }

    def open_aux_uart(self, baud=115200, bits=8, parity=None, stop=1):
        """Open auxiliary field UART1 (GP4 TX / GP5 RX) without touching UART0 COM4 dupterm."""
        self.close_aux_uart()
        if machine is None:
            return None
        try:
            self._aux_uart = machine.UART(
                UART_AUX_BUS,
                baudrate=int(baud),
                bits=int(bits),
                parity=parity,
                stop=int(stop),
                tx=machine.Pin(PIN_AUX_UART_TX),
                rx=machine.Pin(PIN_AUX_UART_RX),
                rxbuf=1024,
            )
            return self._aux_uart
        except Exception:
            self._aux_uart = None
            return None

    def close_aux_uart(self):
        if self._aux_uart is not None:
            try:
                if hasattr(self._aux_uart, "deinit"):
                    self._aux_uart.deinit()
            except Exception:
                pass
            self._aux_uart = None

    def ensure_serial_repl(self):
        """
        Keep active dupterm REPL stream intact without calling os.dupterm(None, 0)
        or re-constructing machine.UART(0) while a session is active.
        """
        return self._uart

    def set_serial_link(self, enabled):
        """
        Gate COM4 (UART0 dupterm + Ctrl+C polling) behind explicit LNK mode.
        When disabled, detaches os.dupterm(None, 0) and drains RX so host serial tools
        cannot communicate until LNK is enabled (cold-boot, BSOD & Safe Recovery re-enable it).
        """
        en = bool(enabled)
        self._serial_link_enabled = en
        if en:
            self.init_uart_bridge(rebind=True)
            return True
        try:
            os.dupterm(None, 0)
        except Exception:
            pass
        if self._uart is not None:
            try:
                n_rx = self._uart.any()
                if n_rx:
                    self._uart.read(n_rx)
            except Exception:
                pass
        return False

    def init_uart_bridge(self, rebind=False):
        """
        Ensure UART(0) GP0/GP1 (CH340 COM4) is attached to os.dupterm(..., 0) at 115200 baud.
        When rebind=True (e.g. on LNK enable, BSOD, Safe Recovery, or after machine.freq() changes),
        re-initializes UART(0) @ 115200 baud and marks serial link active.
        """
        if rebind:
            self._serial_link_enabled = True
        if machine is not None and (rebind or self._uart is None):
            try:
                self._uart = machine.UART(UART_BRIDGE_BUS, UART_BAUDRATE, rxbuf=4096)
                os.dupterm(self._uart, 0)
            except Exception:
                pass
        return self._uart

    def serial_print(self, *args):
        """Print diagnostic text via paced print() so 115200 baud UART0 TX never overflows."""
        self.uart_write_line(" ".join(str(a) for a in args))

    def uart_write_line(self, text):
        """Write a line via 24-byte / 4ms paced print() (routed over active os.dupterm)."""
        s = str(text)
        n = len(s)
        if n <= 24:
            print(s)
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(4)
            return
        for i in range(0, n, 24):
            end = "\n" if (i + 24 >= n) else ""
            print(s[i:i + 24], end=end)
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(4)

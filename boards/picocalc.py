# PinhOS Phase 1 — ClockworkPi PicoCalc Hardware Driver (boards/picocalc.py)
# Encapsulates all PicoCalc (RP2350 Pico 2W + STM32 Southbridge + 320x320 SPI LCD + SPI SD) pins & buses.

import os
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
SD_BAUDRATE  = 12_000_000

# Audio: Dual PWM Piezo / Speaker Outputs
PIN_AUDIO_L  = 26
PIN_AUDIO_R  = 27

# Serial Bridge: UART0
UART_BRIDGE_BUS = 0
PIN_UART_TX     = 0
PIN_UART_RX     = 1
UART_BAUDRATE   = 115200

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
        self._stdin_poll = None
        self._kbuf = bytearray(8)
        self._lut = _build_default_lut()
        self._refresh_active = False
        self._fb_buf = None
        self._fb = None
        self._bat_cache = {
            "percent": 100,
            "voltage_mv": 4150,
            "charging": False,
            "present": True,
        }
        self._last_bat_ms = 0

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
        self.set_lut(self._lut)
        self.set_backlight(self._backlight_pct)
        self.set_kb_backlight(self._kb_backlight_pct)
        self.clear_input()
        self.initialized = True
        return True

    def restore_state(self):
        """Restore default LUT, display auto-refresh, and clear input after sandbox exit."""
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
        """Restore factory 16-entry RGB565 LUT (used by BSOD and Safe Recovery Mode)."""
        self.set_lut(_build_default_lut())

    def stop_refresh(self):
        if self._disp is not None and hasattr(self._disp, "stopRefresh"):
            if self._refresh_active:
                try:
                    self._disp.stopRefresh()
                except Exception:
                    pass
                self._refresh_active = False

    def recover_refresh(self, force=False):
        if self._disp is not None and hasattr(self._disp, "recoverRefresh"):
            if force or not self._refresh_active:
                try:
                    self._disp.recoverRefresh()
                except Exception:
                    pass
                self._refresh_active = True

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

        # Standalone STM32 modifier keycodes (Shift, Ctrl, Alt, Sym/Caps)
        if len(b) == 1 and b[0] in (0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            if b[0] in (0xA1, 0xA2):
                mods |= MOD_SHIFT
            elif b[0] == 0xA3:
                mods |= MOD_CTRL
            elif b[0] == 0xA4:
                mods |= MOD_ALT
            elif b[0] == 0xA5:
                mods |= MOD_SYM
            self._modifiers = mods
            return (None, mods)

        # Function keys F1..F10
        if b"\x81" in b or b.startswith(b"\x1bOP") or b.startswith(b"\x1b[11~"):
            return ("F1", mods)
        if b"\x82" in b or b.startswith(b"\x1bOQ") or b.startswith(b"\x1b[12~"):
            return ("F2", mods)
        if b"\x83" in b or b.startswith(b"\x1bOR") or b.startswith(b"\x1b[13~"):
            return ("F3", mods)
        if b"\x84" in b or b.startswith(b"\x1bOS") or b.startswith(b"\x1b[14~"):
            return ("F4", mods)
        if b"\x85" in b or b.startswith(b"\x1b[15~"):
            return ("F5", mods)
        if b"\x86" in b or b.startswith(b"\x1b[17~"):
            return ("F6", mods)
        if b"\x87" in b or b.startswith(b"\x1b[18~"):
            return ("F7", mods)
        if b"\x88" in b or b.startswith(b"\x1b[19~"):
            return ("F8", mods)
        if b"\x89" in b or b.startswith(b"\x1b[20~"):
            return ("F9", mods)
        if b"\x8a" in b or b"\x90" in b or b.startswith(b"\x1b[21~"):
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
            if state == 3:
                if code in (0xA1, 0xA2):
                    self._modifiers &= ~MOD_SHIFT
                elif code == 0xA3:
                    self._modifiers &= ~MOD_CTRL
                elif code == 0xA4:
                    self._modifiers &= ~MOD_ALT
                elif code == 0xA5:
                    self._modifiers &= ~MOD_SYM
                continue

            # Key pressed (state == 1) or held (state == 2)
            if state in (1, 2):
                if code in (0xA1, 0xA2):
                    self._modifiers |= MOD_SHIFT
                    continue
                if code == 0xA3:
                    self._modifiers |= MOD_CTRL
                    continue
                if code == 0xA4:
                    self._modifiers |= MOD_ALT
                    continue
                if code == 0xA5:
                    self._modifiers |= MOD_SYM
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

        # 1. Direct STM32 I2C keyboard controller (via picocalc.keyboard.keyEvent() / 0x1F)
        raw = self._poll_i2c_keyboard()

        # 2. Only fall back to sys.stdin polling when no physical keyboard/I2C bus is present
        # (avoids sys.stdin.read(1) blocking ui_loop() on RP2350 when UART0 dupterm is active)
        if raw is None and self._kb is None and self._i2c is None:
            raw = self._poll_stdin_nonblocking()

        if raw:
            key_name, mods = self._decode_raw_key(raw)
            self._modifiers = mods
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
        """Non-blocking key poll returning the next key string or None."""
        return self.read_key()

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

    def mount_sd(self, mount_point="/sd", retries=3):
        """Mount the PicoCalc SPI0 microSD card with automatic retry backoff."""
        self._sd_mount_point = mount_point
        if self.is_sd_mounted(mount_point):
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

    def set_backlight(self, percent):
        """
        Set LCD backlight brightness (0..100%).
        Caches requested 0..100% value locally so get_backlight() is deterministic
        even when the STM32 I2C register (0x1F, reg 0x05) is quantized or write-only.
        """
        pct = max(0, min(100, int(round(percent))))
        self._backlight_pct = pct
        if self._kb is not None and hasattr(self._kb, "setBacklight"):
            try:
                self._kb.setBacklight(pct)
                return True
            except Exception:
                pass
        if self._i2c is not None:
            try:
                self._i2c.writeto_mem(SB_I2C_ADDR, REG_SB_LCD_BKL, bytes([pct]))
                return True
            except Exception:
                pass
        return True

    def get_backlight(self):
        """Return active LCD backlight percentage (0..100%)."""
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
        if not self.config.get("sound", True) or volume <= 0:
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

    def stop_audio(self):
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

    def ensure_serial_repl(self):
        """
        Keep active dupterm REPL stream intact without calling os.dupterm(None, 0)
        or re-constructing machine.UART(0) while a session is active.
        """
        return self._uart

    def init_uart_bridge(self):
        return self.ensure_serial_repl()

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

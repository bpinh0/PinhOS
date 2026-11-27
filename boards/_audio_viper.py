# PinhOS — RP2350 Cortex-M33 Viper PWM Audio Feeder (boards/_audio_viper.py)
# Compiled with mpy-cross -O2 -march=armv7emsp into native ARM Thumb-2 machine code.
# Writes both GP26 (PWM5A Left) and GP27 (PWM5B Right) in a single 32-bit bus store
# (< 0.3 us/sample) paced by RP2350 TIMER0 TIMERAWL (0x400B0028, 1 MHz monotonic).

import micropython


@micropython.viper
def pack_pwm(src_buf, dst_u32, n: int, bits: int, ch: int, top: int) -> int:
    """Convert raw PCM bytes into packed 32-bit (R<<16)|L PWM5_CC words for rp2.DMA (0 alloc)."""
    src = ptr8(src_buf)
    dst = ptr32(dst_u32)
    i: int = 0
    k: int = 0
    if bits == 8:
        if ch == 1:
            while i < n:
                s: int = (src[i] * top) >> 8
                dst[k] = (s << 16) | s
                i += 1
                k += 1
        else:
            lim: int = n - 1
            while i < lim:
                sl: int = (src[i] * top) >> 8
                sr: int = (src[i + 1] * top) >> 8
                dst[k] = (sr << 16) | sl
                i += 2
                k += 1
    else:
        if ch == 1:
            lim: int = n - 1
            while i < lim:
                u: int = (src[i] | (src[i + 1] << 8)) ^ 0x8000
                s: int = (u * top) >> 16
                dst[k] = (s << 16) | s
                i += 2
                k += 1
        else:
            lim: int = n - 3
            while i < lim:
                ul: int = (src[i] | (src[i + 1] << 8)) ^ 0x8000
                ur: int = (src[i + 2] | (src[i + 3] << 8)) ^ 0x8000
                sl: int = (ul * top) >> 16
                sr: int = (ur * top) >> 16
                dst[k] = (sr << 16) | sl
                i += 4
                k += 1
    return k


@micropython.viper
def feed_pwm(buf, n: int, bits: int, ch: int, dt_us: int, top: int):
    src = ptr8(buf)
    pwm_cc = ptr32(0x400A8070)
    tim_lo = ptr32(0x400B0028)
    i: int = 0
    nxt: int = tim_lo[0]
    if bits == 8:
        if ch == 1:
            while i < n:
                s: int = (src[i] * top) >> 8
                pwm_cc[0] = (s << 16) | s
                i += 1
                nxt += dt_us
                while (tim_lo[0] - nxt) < 0:
                    pass
        else:
            lim: int = n - 1
            while i < lim:
                sl: int = (src[i] * top) >> 8
                sr: int = (src[i + 1] * top) >> 8
                pwm_cc[0] = (sr << 16) | sl
                i += 2
                nxt += dt_us
                while (tim_lo[0] - nxt) < 0:
                    pass
    else:
        if ch == 1:
            lim: int = n - 1
            while i < lim:
                u: int = (src[i] | (src[i + 1] << 8)) ^ 0x8000
                s: int = (u * top) >> 16
                pwm_cc[0] = (s << 16) | s
                i += 2
                nxt += dt_us
                while (tim_lo[0] - nxt) < 0:
                    pass
        else:
            lim: int = n - 3
            while i < lim:
                ul: int = (src[i] | (src[i + 1] << 8)) ^ 0x8000
                ur: int = (src[i + 2] | (src[i + 3] << 8)) ^ 0x8000
                sl: int = (ul * top) >> 16
                sr: int = (ur * top) >> 16
                pwm_cc[0] = (sr << 16) | sl
                i += 4
                nxt += dt_us
                while (tim_lo[0] - nxt) < 0:
                    pass


# RP2350 PWM Slice 5 (GP26=ChA Left, GP27=ChB Right) & DMA Pacing Timer 0
_PWM5_CC  = 0x400A8070
_PWM5_TOP = 0x400A8074
_DMA_TMR0 = 0x50000440


class WavDmaPlayer:
    """Lazy-loaded RP2350 dual-channel hardware-chained rp2.DMA WAV player (0 B SRAM when idle)."""

    def __init__(self, pin_l=26, pin_r=27):
        self._pin_l = pin_l
        self._pin_r = pin_r
        self._f = None
        self._pwm_l = None
        self._pwm_r = None
        self._buf = None
        self._mv = None
        self._rate = 0
        self._ch = 1
        self._bits = 8
        self._total = 0
        self._rem = 0
        self._bps = 1
        self._us = 125
        self._top = 0
        self._dma = None
        self._ctrl = None
        self._dma_bufs = None
        self._cur = 0
        self._armed = None
        self.err = ""

    def play(self, path):
        import array, struct
        try:
            import machine
        except ImportError:
            machine = None
        self.stop()
        self.err = ""
        f = None
        try:
            f = open(path, "rb")
            hdr = f.read(12)
            if len(hdr) < 12 or hdr[0:4] != b"RIFF" or hdr[8:12] != b"WAVE":
                self.err = "Not a RIFF/WAVE file"
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
                        self.err = "Truncated fmt chunk"
                        f.close()
                        return False
                    afmt, ch, rate, _, _, bits = struct.unpack("<HHIIHH", fb)
                    if csz > 16:
                        f.seek(csz - 16, 1)
                    if csz & 1:
                        f.seek(1, 1)
                    if afmt != 1 or ch not in (1, 2) or bits not in (8, 16) or rate < 8000 or rate > 22050:
                        self.err = "Need PCM 8/16b 8-22kHz"
                        f.close()
                        return False
                    fmt_ok = True
                elif cid == b"data":
                    data_sz = csz
                    break
                else:
                    f.seek(csz + (csz & 1), 1)
            if (not fmt_ok) or data_sz <= 0:
                self.err = "Missing PCM data chunk"
                f.close()
                return False
            self._buf = bytearray(4096)
            self._mv = memoryview(self._buf)
            self._top = 0
            if machine is not None:
                self._pwm_l = machine.PWM(machine.Pin(self._pin_l))
                self._pwm_r = machine.PWM(machine.Pin(self._pin_r))
                self._pwm_l.freq(62500)
                self._pwm_r.freq(62500)
                self._pwm_l.duty_u16(32768)
                self._pwm_r.duty_u16(32768)
                try:
                    t = int(machine.mem32[_PWM5_TOP]) & 0xFFFF
                    if 100 <= t <= 65535:
                        self._top = t
                except Exception:
                    self._top = 0
            self._f = f
            self._rate = rate
            self._ch = ch
            self._bits = bits
            self._total = data_sz
            self._rem = data_sz
            self._bps = max(1, rate * ch * (bits // 8))
            self._us = max(40, 1000000 // rate)
            # RP2350 dual-channel hardware-chained rp2.DMA ping-pong (0 ns gap, 1.000x pitch)
            if machine is not None and self._top > 0:
                try:
                    import rp2
                    if hasattr(rp2, "DMA"):
                        div_y = max(1, min(65535, int(machine.freq()) // rate))
                        machine.mem32[_DMA_TMR0] = (1 << 16) | div_y
                        self._dma_bufs = (array.array("I", bytearray(8192)), array.array("I", bytearray(8192)))
                        d0 = rp2.DMA()
                        d1 = rp2.DMA()
                        self._dma = (d0, d1)
                        c_chain = (
                            d0.pack_ctrl(size=2, inc_read=True, inc_write=False, treq_sel=0x3B, chain_to=d1.channel),
                            d1.pack_ctrl(size=2, inc_read=True, inc_write=False, treq_sel=0x3B, chain_to=d0.channel),
                        )
                        c_stop = (
                            d0.pack_ctrl(size=2, inc_read=True, inc_write=False, treq_sel=0x3B, chain_to=d0.channel),
                            d1.pack_ctrl(size=2, inc_read=True, inc_write=False, treq_sel=0x3B, chain_to=d1.channel),
                        )
                        self._ctrl = (c_chain, c_stop)
                        self._cur = 0
                        self._armed = [False, False]
                        c0 = self._fill(0)
                        c1 = self._fill(1) if c0 > 0 else 0
                        if c0 > 0:
                            if c1 > 0:
                                d1.config(
                                    read=self._dma_bufs[1],
                                    write=_PWM5_CC,
                                    count=c1,
                                    ctrl=c_chain[1] if self._rem > 0 else c_stop[1],
                                    trigger=False,
                                )
                                self._armed[1] = True
                                d0.config(
                                    read=self._dma_bufs[0],
                                    write=_PWM5_CC,
                                    count=c0,
                                    ctrl=c_chain[0],
                                    trigger=True,
                                )
                            else:
                                d0.config(
                                    read=self._dma_bufs[0],
                                    write=_PWM5_CC,
                                    count=c0,
                                    ctrl=c_stop[0],
                                    trigger=True,
                                )
                            self._armed[0] = True
                except Exception:
                    if self._dma is not None:
                        for _d in self._dma:
                            try:
                                _d.active(0)
                                _d.close()
                            except Exception:
                                pass
                    self._dma = None
                    self._ctrl = None
                    self._dma_bufs = None
                    self._armed = None
            return True
        except Exception as e:
            self.err = str(e)[:32]
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass
            self.stop()
            return False

    def _fill(self, slot):
        f = self._f
        rem = self._rem
        if f is None or rem <= 0 or self._dma_bufs is None:
            return 0
        bps_frame = self._ch * (self._bits // 8)
        max_b = min(4096, 2048 * bps_frame)
        want = max_b if rem >= max_b else rem
        try:
            n = f.readinto(self._mv[:want])
        except Exception:
            return 0
        if not n:
            self._rem = 0
            return 0
        self._rem = rem - n
        return int(pack_pwm(self._buf, self._dma_bufs[slot], n, self._bits, self._ch, self._top))

    def step(self):
        if self._dma is not None:
            dmas = self._dma
            cur = self._cur
            if dmas[cur].active():
                return True
            nxt = 1 - cur
            c_chain, c_stop = self._ctrl
            c = self._fill(cur) if self._rem > 0 else 0
            if c > 0:
                dmas[cur].config(
                    read=self._dma_bufs[cur],
                    write=_PWM5_CC,
                    count=c,
                    ctrl=c_chain[cur] if self._rem > 0 else c_stop[cur],
                    trigger=False,
                )
                self._armed[cur] = True
                if self._armed[nxt] and not dmas[nxt].active():
                    dmas[cur].active(1)
                    return True
            else:
                self._armed[cur] = False
            self._cur = nxt
            if not self._armed[nxt] or (not dmas[nxt].active() and not self._armed[cur]):
                self.stop()
                return False
            return True
        f = self._f
        rem = self._rem
        if f is None or rem <= 0:
            if f is not None:
                self.stop()
            return False
        want = 4096 if rem >= 4096 else rem
        try:
            n = f.readinto(self._mv[:want])
        except Exception:
            self.stop()
            return False
        if not n:
            self.stop()
            return False
        self._rem = rem - n
        if self._pwm_l is not None and self._pwm_r is not None and self._top > 0:
            feed_pwm(self._buf, n, self._bits, self._ch, self._us, self._top)
        if self._rem <= 0:
            self.stop()
            return False
        return True

    def playing(self):
        if self._dma is not None:
            try:
                if self._dma[0].active() or self._dma[1].active():
                    return True
                if self._armed and (self._armed[0] or self._armed[1]):
                    return True
            except Exception:
                pass
        return bool(self._f is not None and self._rem > 0)

    def status(self):
        played = max(0, self._total - self._rem)
        bps = max(1, self._bps)
        return {
            "playing": self.playing(),
            "pos_s": played // bps,
            "dur_s": self._total // bps,
            "rate": self._rate,
            "ch": self._ch,
            "bits": self._bits,
            "error": self.err,
        }

    def stop(self):
        try:
            import machine
        except ImportError:
            machine = None
        if self._dma is not None:
            for _d in self._dma:
                try:
                    _d.active(0)
                    _d.close()
                except Exception:
                    pass
            try:
                if machine is not None:
                    machine.mem32[_DMA_TMR0] = 0
            except Exception:
                pass
            self._dma = None
        self._ctrl = None
        self._dma_bufs = None
        self._armed = None
        if self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None
        self._rem = 0
        self._buf = None
        self._mv = None
        for attr in ("_pwm_l", "_pwm_r"):
            p = getattr(self, attr, None)
            if p is not None:
                try:
                    p.duty_u16(0)
                    p.deinit()
                except Exception:
                    pass
                setattr(self, attr, None)
        if machine is not None:
            for pin_id in (self._pin_l, self._pin_r):
                try:
                    pwm = machine.PWM(machine.Pin(pin_id))
                    pwm.duty_u16(0)
                    pwm.deinit()
                except Exception:
                    pass

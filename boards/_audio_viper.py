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

# PinhOS Phase 5.4 — Two-Stage Soft + Hard Watchdog Supervisor (core/watchdog.py)
# Stage 1: 2s periodic machine.Timer feeds the 8s RP2350 silicon WDT as long as Core 0
#          & IRQ subsystem are alive, while tracking heartbeat stalls against a configurable
#          soft timeout (15s / 30s / 60s / OFF) and scheduling an IRQ-safe 'NOT RESPONDING'
#          Wait / Abort / Reboot dialog via micropython.schedule().
# Stage 2: RP2350 hardware machine.WDT (8s) remains armed underneath for true deadlocks.
# Zero hardcoded GPIO pins; zero heap allocations inside timer IRQ.

import sys
import time

try:
    import machine
except Exception:
    machine = None

try:
    import micropython
except Exception:
    micropython = None


class SoftWatchdogAbort(Exception):
    """Raised when the user selects [ESC] Abort in the Soft Watchdog 'Not Responding' dialog."""
    pass


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else int(a - b)


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(int(ms))
    else:
        time.sleep(ms / 1000.0)


class TwoStageWatchdog:
    """
    Two-Stage Soft + Hard Watchdog for RP2350 (Issue #54).
    Exposes .feed() so every existing __pinhos_wdt__.feed() caller updates the soft heartbeat.
    """

    def __init__(self, hw_timeout_ms=8000, soft_timeout_s=30, board=None, ui=None, logger=None, arm_hw=True):
        self.hw_timeout_ms = min(8388, max(1000, int(hw_timeout_ms or 8000)))
        self._soft_ms = max(0, int(soft_timeout_s or 0)) * 1000
        self.board = board
        self.ui = ui
        self.logger = logger
        self._hw_wdt = None
        self._timer = None
        self._paused = False
        self._prompt_active = False
        self._last_hb_ms = _ticks_ms()
        self._last_op = "IDLE"
        # Pre-bind callback references once to guarantee zero allocation in timer IRQ
        self._timer_cb = self._on_timer
        self._sched_cb = self._on_soft_timeout

        if arm_hw and machine is not None and hasattr(machine, "WDT"):
            # Try Stage 1 periodic timer BEFORE/independently of silicon WDT so an
            # exhausted RP2350 alarm pool (OSError 12 / ENOMEM) NEVER strands an unfed WDT.
            if hasattr(machine, "Timer"):
                try:
                    self._timer = machine.Timer(
                        -1,
                        period=2000,
                        mode=machine.Timer.PERIODIC,
                        callback=self._timer_cb,
                    )
                except Exception:
                    try:
                        self._timer = machine.Timer(
                            period=2000,
                            mode=machine.Timer.PERIODIC,
                            callback=self._timer_cb,
                        )
                    except Exception:
                        self._timer = None
            self._hw_wdt = machine.WDT(timeout=self.hw_timeout_ms)

    def attach(self, board=None, ui=None, logger=None):
        if board is not None:
            self.board = board
        if ui is not None:
            self.ui = ui
        if logger is not None:
            self.logger = logger

    def set_soft_timeout_s(self, seconds):
        s = max(0, int(seconds or 0))
        self._soft_ms = s * 1000
        self._last_hb_ms = _ticks_ms()
        return s

    def get_soft_timeout_s(self):
        return self._soft_ms // 1000

    def set_op(self, op_label):
        self._last_op = str(op_label or "IDLE")[:32]
        self._last_hb_ms = _ticks_ms()

    def pause(self):
        """Suppress soft-timeout prompts (e.g. during REPL standby or Sleep) while keeping Stage 2 fed."""
        self._paused = True
        self._last_hb_ms = _ticks_ms()

    def resume(self):
        self._last_hb_ms = _ticks_ms()
        self._prompt_active = False
        self._paused = False

    def feed(self):
        """Update Stage 1 soft heartbeat and feed Stage 2 hardware WDT."""
        self._last_hb_ms = _ticks_ms()
        w = self._hw_wdt
        if w is not None:
            try:
                w.feed()
            except Exception:
                pass

    def _on_timer(self, _t):
        # Strictly zero heap allocations inside timer IRQ!
        w = self._hw_wdt
        if w is not None:
            w.feed()
        if self._paused or self._prompt_active or self._soft_ms <= 0:
            return
        if _ticks_diff(_ticks_ms(), self._last_hb_ms) >= self._soft_ms:
            self._prompt_active = True
            if micropython is not None and hasattr(micropython, "schedule"):
                try:
                    micropython.schedule(self._sched_cb, 0)
                except Exception:
                    self._prompt_active = False

    def _log_wdt(self, msg):
        lg = self.logger
        if lg is not None:
            try:
                if hasattr(lg, "log_wdt"):
                    lg.log_wdt(msg)
                else:
                    lg.warn("WDT: " + msg)
            except Exception:
                pass

    def _draw_not_responding(self, elapsed_s):
        b = self.board
        if b is None:
            return
        try:
            b.fill_rect(14, 72, 292, 168, 0)
            b.rect(14, 72, 292, 168, 11)
            b.fill_rect(16, 74, 288, 22, 11)
            b.text("NOT RESPONDING (SOFT WDT)", 24, 81, 0)
            b.text("No heartbeat for {}s".format(elapsed_s), 24, 106, 15)
            b.text(("Op: " + self._last_op)[:42], 24, 122, 6)
            b.hline(20, 140, 280, 11)
            b.text("[W / ENT] Wait another {}s".format(max(15, self.get_soft_timeout_s())), 24, 150, 10)
            b.text("[ESC / A] Abort to Desktop", 24, 168, 11)
            b.text("[R]       Reboot PinhOS", 24, 186, 9)
            b.hline(20, 208, 280, 11)
            b.text("Stage 2 8s HW WDT stays active", 24, 218, 6)
            b.show()
        except Exception:
            pass

    def prompt_not_responding(self, elapsed_s=None):
        """
        Show Windows-style 'Not Responding' Wait / Abort / Reboot prompt.
        Returns 'wait', raises SoftWatchdogAbort on 'abort', or resets on 'reboot'.
        """
        el_s = int(elapsed_s) if elapsed_s is not None else max(1, _ticks_diff(_ticks_ms(), self._last_hb_ms) // 1000)
        self._log_wdt("SOFT_TIMEOUT ({}s) op={}".format(el_s, self._last_op))
        b = self.board
        if b is None:
            self._last_hb_ms = _ticks_ms()
            self._prompt_active = False
            return "wait"

        self._draw_not_responding(el_s)
        poll_fn = getattr(b, "read_key", None) or getattr(b, "poll_key", None)
        choice = "wait"
        try:
            while True:
                k = poll_fn() if poll_fn else None
                if k:
                    ku = str(k).upper()
                    if ku in ("W", "ENTER", "RETURN", "SPACE", " "):
                        b.beep(1300, 12)
                        choice = "wait"
                        break
                    if ku in ("ESC", "BACK", "BACKSPACE", "A"):
                        b.beep(950, 15)
                        choice = "abort"
                        break
                    if ku == "R":
                        b.beep(800, 20)
                        choice = "reboot"
                        break
                _sleep_ms(30)
        except KeyboardInterrupt:
            choice = "abort"
        finally:
            self._last_hb_ms = _ticks_ms()
            self._prompt_active = False

        if choice == "reboot":
            self._log_wdt("SOFT_WDT: User selected REBOOT")
            try:
                from core.config import save_rtc_state
                save_rtc_state(b)
            except Exception:
                pass
            if self.logger is not None:
                try:
                    self.logger.clear_breadcrumb("CLEAN_EXIT")
                except Exception:
                    pass
            if machine is not None and hasattr(machine, "reset"):
                machine.reset()
            return "reboot"

        if choice == "abort":
            self._log_wdt("SOFT_WDT: User selected ABORT")
            raise SoftWatchdogAbort("Aborted unresponsive op ({}s)".format(el_s))

        self._log_wdt("SOFT_WDT: User selected WAIT")
        if self.ui is not None and hasattr(self.ui, "mark_all_dirty"):
            try:
                self.ui.mark_all_dirty(True)
                self.ui.render(force=True)
            except Exception:
                pass
        return "wait"

    def _on_soft_timeout(self, _arg):
        if self._paused or self._soft_ms <= 0:
            self._prompt_active = False
            return
        el_ms = _ticks_diff(_ticks_ms(), self._last_hb_ms)
        if el_ms < self._soft_ms:
            self._prompt_active = False
            return
        self.prompt_not_responding(el_ms // 1000)

    def deinit(self):
        self._paused = True
        if self._timer is not None:
            try:
                self._timer.deinit()
            except Exception:
                pass
            self._timer = None

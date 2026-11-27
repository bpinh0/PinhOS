# PinhOS App Developer Guide (SDK v1)

PinhOS runs third-party MicroPython apps from `/sd/pinhos/apps/*.py` inside an isolated **`SandboxRunner`** (`core/sandbox.py`). Every app is statically validated **before** a single line of code is compiled or executed — non-compliant apps are blocked automatically to protect OS stability, SRAM integrity, and Core 1 display refresh on the RP2350 PicoCalc.

---

## 1. Quick Start

1. Copy the official starter template:
   ```
   docs/templates/app_template.py  ->  apps/my_app.py
   ```
2. Update `APP_META` (`id`, `name`, `min_sram`, `min_block`, `needs_radio`).
3. Validate locally on PC in < 1 second before deploying:
   ```powershell
   .\picocalc.ps1 lint apps\my_app.py
   ```
4. Deploy via **WebPortal IDE** (`Shift+F6` → Live Run / Save to `/sd/pinhos/apps/`) or copy to `/sd/pinhos/apps/my_app.py` on the SD card.
5. Launch from **`Apps & Studio`** on the PicoCalc.

---

## 2. Mandatory `APP_META` Contract

`APP_META` **must** be a static Python dictionary literal (no variables or function calls) inside the **first 1.5 KB** of your `.py` file.

| Key | Required | Type / Constraint | Description |
| --- | --- | --- | --- |
| `id` | Yes | `str` (`2..24` chars, `[a-z0-9_]`, starts with `a-z`) | Unique app ID (also names swap state & `app_<id>.log`). |
| `name` | Yes | non-empty `str` | Display name in `Apps & Studio`. |
| `version` | Yes | non-empty `str` | Semantic version (e.g. `"1.0.0"`). |
| `category` | Yes | non-empty `str` | Menu category (e.g. `"Utility"`, `"Network"`, `"Media"`). |
| `entry` | Yes | non-empty `str` | Function name (typically `"main"`), defined as `def main(ctx):`. |
| `min_sram` | Yes | `int >= 16384` | Minimum free SRAM (bytes) required before launch. |
| `ui_modes` | Yes | non-empty `list[str]` | Subset of `["gui", "tui", "native"]`. |
| `min_block` | Recommended | `int >= 0` (default `16384`) | Minimum **contiguous** free SRAM block (bytes). |
| `needs_radio` | Optional | `bool` (default `False`) | Set `True` if using Wi-Fi/BLE; OS pauses WebPortal cleanly while running. |
| `description` | Optional | `str` | Short 1-line description. |
| `native_libs` | Optional | `list[str]` | Reserved for optional native `.mpy` modules. |

---

## 3. `AppContext` (`ctx`) API

Your entry function receives `ctx`:

- **`ctx.board`** — Board HAL (`fill`, `fill_rect`, `rect`, `hline`, `vline`, `line`, `pixel`, `text`, `show`, `beep`, `poll_key`, `clear_input`, `get_modifiers`, `get_battery`, `get_timestamp_str`, `get_sd_stats`).
- **`ctx.theme`** — Active theme (`ctx.theme.color("bg"|"surface"|"border"|"accent"|"accent_fg"|"text"|"text_muted"|"ok"|"warn"|"err")`).
- **`ctx.ui`** — Active `UIEngine` (`ctx.ui.mode` is `"gui"` or `"tui"`).
- **`ctx.open(path, mode)`** / **`ctx.socket(...)`** — Resource-tracked file & socket handles (automatically closed on exit or crash).
- **`ctx.save_state(dict)`** / **`ctx.load_state(default={})`** — Persistent SD swap state under `/sd/pinhos/swap/<id>.json`.
- **`ctx.yield_(step_web=True)`** — Feeds the OS watchdog and cooperatively steps WebPortal/CYW43 during long operations (pass `step_web=False` during Wi-Fi scans).
- **`ctx.log(msg)`** — Appends a compact timestamped note with live heap metrics to `/sd/pinhos/logs/app_<id>.log` (auto-capped at 4 KB, viewable in `[CTRL+L] Logs`).
- **`ctx.args`** — Optional launch arguments `dict`.

---

## 4. Strict Pre-Flight Safeguards (`SandboxPolicyError`)

To prevent crashes, Core 1 LCD lockups, and unexpected reboots, `SandboxRunner` statically scans every app **before** compiling or importing it and **refuses to run** if any forbidden pattern is present:

| Forbidden Pattern | Why It Is Blocked | Safe Replacement |
| --- | --- | --- |
| `machine.Pin` / `from machine import Pin` | Hardcoded GPIO pins break portability and can corrupt SPI/I2C/PSRAM buses. | `ctx.board` HAL |
| `machine.WDT` / `__pinhos_wdt__` | Interferes with the OS Two-Stage Watchdog. | `ctx.board.poll_key()` & `ctx.yield_()` |
| `machine.reset()` / `soft_reset()` / `deepsleep()` | Sudden unlogged reboot or lockup. | Return from `main(ctx)` |
| `os.dupterm()` | Breaks COM4 UART0 serial link / REPL recovery. | `ctx.log(...)` |
| `stopRefresh()` / `recoverRefresh()` | Repeated calls wedge RP2350 Core 1 LCD DMA (blank screen). | `ctx.board.show()` |
| `board.poll_input(` | Returns an `int` event count (`0`), causing 100% CPU freeze loops. | `ctx.board.poll_key()` |
| `_pinhos_main` | Internal OS singleton state must remain isolated. | `ctx` APIs |

---

## 5. Memory, Input & ANR Rules

1. **SRAM & Fragmentation:** RP2350 has 520 KB SRAM shared with MicroPython, Core 1, and optional lwIP/WebPortal.
   - Never allocate full-screen Python framebuffers (draw directly via `ctx.board.*` primitives).
   - Stream files in `<= 1024`-byte chunks.
   - Call `gc.collect()` before heavy allocations or `wlan.scan()`.
2. **Responsive Input Loop:**
   - Always poll with `ctx.board.poll_key()` and sleep `time.sleep_ms(30)` when idle.
   - Always support **`ESC`** (or `Q`/`BACKSPACE`) to exit cleanly.
3. **OS-Level ANR & Crash Isolation:**
   - **Per-app logs:** Unhandled exceptions or `MemoryError` are caught by `SandboxRunner`, logged with `Heap: <free>K free | <blk>K blk | <used>K used` (plus `(FRAG!)`/`(LOW!)` tags) to **`/sd/pinhos/logs/app_<id>.log`**, and summarized in 2 lines in `crash.log`.
   - **Android-style ANR (`ALT+F5`):** Pressing **`ALT+F5`** inside any app opens **`!! APP NOT RESPONDING !!`** (`[W/ENT] Keep Waiting` or `[K/ESC] Force Close App`), allowing the user to terminate a stuck app and reclaim all RAM/handles without rebooting the OS.
   - **Hardware WDT:** True infinite busy loops (`while True: pass`) are recovered automatically by the 8s RP2350 hardware watchdog with a breadcrumb in `wdt.log`.

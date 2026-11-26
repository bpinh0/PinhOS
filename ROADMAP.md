# 🌲 PinhOS — Architectural Specification & Engineering Roadmap

> **Target Platform:** ClockworkPi PicoCalc (Raspberry Pi Pico 2W / RP2350 — Dual ARM Cortex-M33 @ 150 MHz, 520 KB SRAM, 4 MB Flash, CYW43439 Wi-Fi 4 + BLE 5.2, 320×320 SPI LCD, I2C STM32 Southbridge, SPI microSD).  
> **Current Status:** Active Development — `v1.0.0-alpha.5.0` (**Phase 1–4.x + Phase 5 Batch 1 Complete & Verified 12/12 Self-Test + Deep Stress Suite on Hardware** — Android-Style Desktop Home Screen with `LEFT`/`RIGHT` quick-strip navigation, simultaneous `SYS TELEMETRY` rows (`IP`/`Offline`, `SIG` + `GUI`/`TUI`, `WEB ON/OFF [S-F6]`, `BL`/`SD`), `<= 1 KB` Quick Notes, standardized `F1`–`F5` & `Shift+F6`–`F10` keybar with `[F1]` Help popup, Extensible **Theme Schema v2** with selectable `570 B` `6×8` bitmap fonts (`default`, `bold`, `retro`, custom `.bin`), widget chrome styles, custom banners & **Obsidian Amber**, periodic/shutdown RTC persistence (`rtc_state.json`) + boot/periodic background NTP sync, **Two-Stage Soft + Hard Watchdog** (`15s`/`30s`/`60s`/`OFF` + "Not Responding" Wait/Abort/Reboot dialog with RP2350 alarm-pool `coop` fallback), **MemGuard** idle/pre-flight SRAM reclaimer, lazy GUI/TUI backends, slimmed `shell.py` (`tools/_shell_cmds.mpy`), and 33-module `.mpy` Core OS Bytecode Deployment; **Phase 5 Batch 2: Async Wi-Fi/SoftAP, Signed Atomic SHA-256 OTA, App Store, Legal Viewer (`#58`) & Date/Time Formats (`#62`) next**).

---

## 1. Core Architectural Pillars & Constraints

1. **95% Python / 5% C & Viper Hybrid Execution:**
   * All OS orchestration, `boards/` HAL drivers, networking, WebPortal routes, and application UI wrappers remain pure MicroPython for rapid iteration, live on-device editing via WebPortal, and over-the-air updates.
   * `@micropython.viper` (`ptr8`/`ptr16`) is reserved for tight pixel-buffer blits and LUT expansions; compiled C `.mpy` dynamic modules (`py/dynruntime.h`) are reserved for real-time DSP, MP3 decoding, and heavy packet parsing (`v1.1.0`).
2. **Deterministic 520 KB SRAM Budget:**
   * Pre-allocate display framebuffers and RGB565 LUT tables during early boot before heap fragmentation occurs.
   * Enforce strict module unloading and descriptor cleanup in `core/sandbox.py` (`< 2 KB` residual heap delta per app lifecycle).
   * Offload dormant task state to `/sd/pinhos/.swap/` via `core/swap.py` whenever switching contexts or crossing low-memory watermarks (`< 64 KB` free).
3. **Strict Hardware Decoupling (`boards/`):**
   * Zero hardcoded GPIO pins, SPI buses, I2C addresses, or display dimensions outside `boards/`.
   * Supporting new hardware (custom RP2350 cyberdecks, external GPIO backpacks, or future ESP32-S3 ports) requires only adding a board profile implementing `boards/base.py`.
4. **Zero-Brick Field Resilience:**
   * Every boot increments a persistent strike counter before loading user configs, themes, or network services. Three consecutive failures automatically drop into **Safe Recovery Mode** (minimal serial + emergency Wi-Fi WebPortal) to repair or roll back broken files.

---

## 2. Standard Contracts & Schemas

### App Entry Contract (`APP_META`)
Every applet in `/sd/pinhos/apps/` or `/sd/pinhos/tools/` exposes a single `main(ctx)` entry point and module-level metadata dictionary so the launcher, Store, and sandbox can validate memory requirements before execution:
```python
APP_META = {
    "id": "uart_term",
    "name": "UART Console",
    "version": "1.0.0",
    "category": "Field Tools",       # Field Tools | Network | System | Media | Games
    "description": "Hardware serial terminal with baud presets and macros",
    "entry": "main",
    "min_sram": 32768,               # Minimum free bytes required before launch
    "ui_modes": ["gui", "tui"],      # Supported rendering backends
    "native_libs": []                # Optional .mpy C dependencies (v1.1.0+)
}

def main(ctx):
    # ctx provides: board, ui, theme, swap, net, config, logger
    ...
```

### Unified Theme Schema (`themes/*.json`)
```json
{
  "name": "Amber Phosphor",
  "id": "amber_phosphor",
  "colors": {
    "bg": "#0A0A0C",
    "surface": "#141619",
    "fg": "#FFB000",
    "fg_muted": "#996A00",
    "accent": "#FFB000",
    "accent_alt": "#00E5FF",
    "border": "#4D3500",
    "ok": "#39FF14",
    "warn": "#FF9500",
    "err": "#FF2A55"
  },
  "font": "font_8x8",
  "border_radius": 2
}
```

---

## 3. Release `v1.0.0` — Foundation & Daily Driver *(Active)*

### Phase 1: Hardware Abstraction, Boot Guard & Resilient Runtime
- [x] **1.1 Canonical Filesystem & Manifest (`version.json`):**
  - Initialize `/sd/pinhos/` directory hierarchy (`boards/`, `core/`, `ui/`, `net/`, `web/`, `tools/`, `apps/`, `themes/`, `.swap/`, `logs/`, `screenshots/`).
  - Create `version.json` containing semantic version, build timestamp, target architecture (`armv7emsp`), and OTA channel metadata.
- [x] **1.2 Board Hardware Abstraction Layer (`boards/`):**
  - `boards/base.py`: Define abstract base class and capability flags for display (`320x320` RGB565 blit/fill), keyboard/pointer input queue, microSD mount/unmount, battery voltage/percentage/charging state, PWM backlight (`0–100%`), PWM/I2S audio, and RTC.
  - `boards/picocalc.py`: Full hardware driver for ClockworkPi PicoCalc (SPI LCD controller, I2C STM32 southbridge keyboard scan + modifier decoding + battery registers, SPI SD card mount with retry logic, keyboard & screen backlight PWM, 4-bit indexed BMP screenshot capture).
  - `boards/generic_spi.py`: Configurable fallback driver for bare Pico 2W setups using standard ST7789/ILI9341 SPI displays and I2C CardKB keyboards.
  - Board auto-detection / `config.json` profile selector at boot.
- [x] **1.3 Crash-Proof 3-Strike Boot Guard (`main.py`):**
  - Read and increment `boot_strikes` in persistent flash state prior to mounting SD or importing UI/network modules.
  - Reset `boot_strikes = 0` only after the main event loop runs cleanly for `5 seconds` (or upon explicit self-test pass).
  - Trigger **Safe Recovery Mode** when `boot_strikes >= 3`: boots with minimal framebuffer text output, USB serial REPL access, and recovery helpers to restore configs or roll back updates.
- [x] **1.4 Sandboxed App Runner (`core/sandbox.py`):**
  - Parse `APP_META` safely without executing top-level app logic; verify `gc.mem_free() >= min_sram`.
  - Snapshot `set(sys.modules.keys())` and track opened file/socket wrappers before invoking `main(ctx)`.
  - In a guaranteed `finally:` block on normal exit or unhandled exception: close leaked descriptors, delete all newly imported modules from `sys.modules`, restore display/input state, and run `gc.collect()`.
- [x] **1.5 Cooperative Swap Manager (`core/swap.py`):**
  - Provide `swap.save(app_id, state_dict)` and `swap.load(app_id)` backed by `/sd/pinhos/.swap/` with automatic stale-swap pruning and corruption checks.
- [x] **1.6 Deployment & Automated Self-Test Gate (`picocalc.ps1` & `tests/selftest.py`):**
  - Ensure `.\picocalc.ps1 upload_and_start` cleanly deploys files over `COM4` Raw REPL (with per-chunk write & signature verification) or `mpremote` and streams the 5s Boot Guard stabilization window.
  - Implement `tests/selftest.py` (`.\picocalc.ps1 test`) verifying: HAL display/I2C/SD init, swap R/W roundtrip, sandbox module cleanup (`< 2048 bytes` SRAM leak tolerance), simulated 3-strike safe-mode trigger, and non-blocking input + frozen `pinhos_boot` & Boot Menu/`Ctrl+C` stability (**6/6 PASS verified on PicoCalc hardware**).
- [x] **1.7 Custom RP2350 Auto-Boot Base Firmware (`firmware/`):**
  - Reproducible WSL2/Linux build pipeline (`firmware/build_uf2.sh`) compiling MicroPython `v1.25.0` (`RPI_PICO2_W`) + `picocalcdisplay` & `vtterminal` C modules into `firmware/dist/pinhos-picocalc-pico2w.uf2`.
  - Frozen early-boot router (`firmware/frozen/_boot.py` & `pinhos_boot.py`) that initializes `PicoDisplay(320, 320)`, `PicoKeyboard()`, and `PicoSD()`, auto-attaches `UART(0)` (`COM4`), dynamically loads `version` & `firmware_version` from `/sd/pinhos/version.json`, renders a staged `0% → 100%` cold-boot progress bar and live `5.0s` countdown, and boots straight into `/sd/pinhos/main.py`.
  - Built-in boot hotkeys: `[ENTER]` instant boot, `[F1]`/`[ESC]` Custom Safe Recovery Mode, `[F2]` crash-proof **Dual-Boot Manager** (dirty-flag rendering + `gc.collect()`), and `[CTRL+C]` (`0xA5` + `c`) immediate REPL interrupt.

---

### Phase 2: Dual-UI Engine & Unified Theme System
- [x] **2.1 Unified Theme Engine (`core/theme.py` & `themes/`):**
  - Load and validate all 4 BOM-free JSON themes (`cyber_amber.json`, `phosphor_green.json`, `arctic_daylight.json`, `synthwave_pulse.json`) with automatic fallback to built-in `cyber_amber` if SD is missing or a file is malformed.
  - Precompute 16-entry RGB565 LUT arrays applied in-place to `boards/picocalc.py` (Core 1-safe, zero full-screen framebuffer allocation) with runtime `[CTRL+T]` hot-swapping and `config.json` persistence.
- [x] **2.2 Shared Widget Toolkit & Dual Rendering Backends (`ui/widgets.py`, `ui/gui.py`, `ui/tui.py`):**
  - Reusable dirty-tracked widgets (`StatusBar`, `FooterBar`, `Panel`, `ListMenu`, `ProgressBar`, `Dialog`, `TextView`) with 2-row partial redraws on `ListMenu` navigation (`delta=0B` SRAM verified on hardware).
  - **GUI Mode (320×320 Graphical):** Framed panels, accent header/footer bars, bordered cards, and graphical progress indicators.
  - **TUI Mode (High-Density Terminal):** Crisp monochrome/accent grid layout, dense list rows, ASCII dividers, and minimal draw overhead.
- [x] **2.3 Seamless Live UI Mode Switcher (`ui/engine.py`):**
  - Switch live between GUI and TUI modes (`[TAB]` / `[CTRL+M]`) and cycle themes (`[CTRL+T]`) with deterministic backend cleanup, `config.json` persistence, and `< 2 KB` SRAM delta (`0 B` verified on hardware).
- [x] **2.4 Crash Forensics, BSOD Guard & On-Device Log Viewer (`core/logger.py` & `main.py`):**
  - Persistent `system.log` / `crash.log` with rotation, `breadcrumb.json` + `machine.reset_cause()` unclean-shutdown detection, `[CTRL+L]` scrollable Dual-UI log viewer, `[ALT+F5]` Hard Reload (`x2` emergency reset), and `show_bsod()` fault fallback (**8/8 PASS verified on PicoCalc hardware**).

---

### Phase 3: Built-In BusyBox CLI & Field Utilities (`tools/`)
- [x] **3.1 Interactive Shell (`tools/shell.py` + `tools/_shell_cmds.py`):**
  - Command-line REPL with 20-entry history ring, path/command tab-completion, environment variables, quote-aware `;` / `|` / `>` / `>>`, bounded 53-column 6×8 scrolling output (`TermView`), and core UNIX-style + hardware commands (`ls`, `cd`, `cat`, `head`, `tail`, `grep`, `wc`, `cp`, `mv`, `rm` with protected-path guard, `mkdir`, `hexdump`, `df`, `free`, `ps`, `uname`, `ver`, `dmesg`/`log`, `bat`, `bl`, `theme`, `mode`, `hwinfo`, `i2cscan`, `com4`, `edit`, `reboot`).
  - Non-blocking `[CTRL+Q]` COM4 Serial Link (`LNK` badge) toggle that rebinds `UART0 @ 115200` on demand (and on BSOD/Safe Recovery/Sandbox fault screens) while keeping the UI 100% responsive and suppressing auto-sleep during REPL sessions.
- [x] **3.2 File Manager & Text Editor (`tools/files.py` & `tools/editor.py`):**
  - Keyboard-driven file browser across `/sd/` and internal flash with file size/type metadata, copy/move/rename/delete/mkdir, streaming 1 KB text/JSON viewer, 8-byte hex dump inspector, and nano-style on-device text/JSON editor (`16 KB` RAM cap + JSON validation).
- [x] **3.3 Network & Hardware Field Utilities (`tools/net_tools.py` & `tools/uart_term.py`):**
  - **Net Probes:** Wi-Fi STA status, DNS resolver, 4× TCP RTT ping, TCP port scanner, local subnet host sweep, and 102-byte Wake-on-LAN (`WoL`) magic packet sender.
  - **UART Serial Console:** HAL-routed auxiliary `UART1` (`GP8`/`GP9`, zero conflict with `UART0` `COM4` or PSRAM) with baud presets (`9600` to `921600`), `8N1`, ASCII/Hex toggle, SD session logging, and programmable F-key macros.
- [x] **3.4 System Monitor, Settings, Screenshots & Hierarchical Mosaic Launcher (`tools/sysmon.py`, `ui/menu.py`, `main.py`, `picocalc.ps1`):**
  - Live primitive-drawn SRAM sparkline, GC cycle counter, RP2350 internal temperature & CPU frequency readout, 1 KB streamed SD read/write benchmark, backlight brightness sliders, and live UI/theme switcher.
  - Evolved the Dual-UI launcher to the 3×2 icon-tile **Mosaic** (GUI) / 1–6 numbered list (TUI) backed by an Android-style hierarchical drill-down menu & Settings tree (`Terminal & Toolkit`, `Files & Editor`, dynamic `Apps & Studio`, `System & Diagnostics`, `Settings`, `Wi-Fi & Network`), dynamic `StatusBar` right-side width reservation, standardized `config.snap.json` snapshots, global `[CTRL+P]` 4-bit BMP screenshot capture with confirmation toast across all menus/tools, `picocalc.ps1 com` & `screenshot` host utilities, and **10/10 PASS verified on PicoCalc hardware**.

---

### Phase 3.1: Android-Style Desktop Home Screen & Settings Overhaul (`v1.0.0-alpha.3.1`)
- [x] **3.1.1 Desktop Home Workspace & App Drawer Navigation (`ui/desktop.py` & `main.py`):**
  - Implemented self-contained `DesktopHome` workspace matching `docs/mockups/` as the primary **Home Screen**, featuring a top quick-category strip (`[1] TOOL`–`[6] NET`) and split cards (`SYS TELEMETRY` live SRAM sparkline/CPU/temp/battery/WLAN + `QUICK NOTES` persistent scratchpad backed by `/sd/pinhos/notes.txt` with `<= 1 KB` streaming R/W, inline `[N]` entry, and `[E]` full editor launch).
  - Provided Android-style two-layer navigation: `ENTER` / `HOME` opens the customizable **App Drawer** (`GRID` 3×2 Mosaic or `LIST` view toggled via `CTRL+V`), while `ESC` returns cleanly to Desktop Home (`boot_screen` configurable between `"desktop"` and `"drawer"` in `config.json`, `0 B` SRAM delta verified in Gate 11).
- [x] **3.1.2 Reorganized 5-Category Settings Architecture (`ui/menu.py`):**
  - Restructured `MENU_TREE["settings"]` into 5 intuitive, intent-grouped categories with live right-aligned state badges (**11/11 PASS verified on PicoCalc hardware**):
    1. **Connectivity & Time** (`[LAN >]` — Wi-Fi Status/Scan/Saved/Auto-Connect/Off, NTP Sync/Auto-NTP/Timezone, GitHub Version/Theme/App Sync)
    2. **Display & Appearance** (`[SCR >]` — Theme, UI Mode `GUI`/`TUI`, App Drawer Style `GRID`/`LIST`, Boot Screen `Home`/`Drawer`, LCD & KB Backlights)
    3. **Status Bar & Sound** (`[UI >]` — Wi-Fi Indicator style, Battery Indicator style, Key Sound/Beep)
    4. **System, Power & Backup** (`[SYS >]` — CPU Clock profile, Auto-Sleep Timer, Sleep Now, Config Snapshot Save/Restore, Battery & RTC Info, Reboot, COM4 Serial Link `LNK`)
    5. **About PinhOS** (`[INF >]` — OS & UF2 Version, Board & SRAM Summary)

---

### Phase 4: WebPortal Browser IDE, `.mpy` Core Bytecode & Field Polish (`web/`) — `v1.0.0-alpha.4`
- [x] **4.1 Embedded Async Web Server (`web/__init__.py`, `web/server.py`):**
  - Cooperative non-blocking `uasyncio` HTTP/REST server stepped from `main.py`'s `ui_loop()` and `ui/menu.py` modal `_idle_wait()` with configurable port (`8080`), auto-start toggle, `WEB` StatusBar badge, auto-sleep suppression, bounded concurrency (`max_conns=6`), active-request burst stepping, `5s` per-request timeout, `<= 1 KB` chunked SD streaming (`Cache-Control: public, max-age=3600`), strict `PINHOS_ROOT` path-traversal guard, `builtins._pinhos_web_srv` orphan-socket cleanup, `board.*` HAL routing, and rotating `/sd/pinhos/logs/web.log` (`16 KB` cap).
  - CYW43439 gSPI RX FIFO pump (`WebServer._pump_wifi()` + `main.py` idle `ui_loop()` poll + `WLAN.PM_NONE` + 5s `WifiManager.status()` cache) eliminating Pico 2W RX stalls (`7ms–49ms` ping, `0%` packet loss).
- [x] **4.2 Cyber-Amber Browser IDE & Virtual Controller (`web/static/`):**
  - Zero-dependency offline 4-tab SPA (`index.html`, `style.css`, `app.js` — `App Studio`, `SD Files`, `Live Console`, `Settings`) served directly from `/sd/pinhos/web/static/`.
  - **App Studio & Virtual Controller:** Line-numbered code editor with `Ctrl+S` streaming save to SD, `compile()` syntax check (`/api/syntax`), remote `SandboxRunner` app launch (`/api/run`), Live 320×320 Device Screen capture (`/api/screenshot`), and interactive Virtual Controller wired to `POST /api/key`.
  - **SD Files, Live Console & Settings:** Browse/create/download/delete under `/sd/pinhos/`, inline BMP previewer, live telemetry bar (`/api/status` including SWAP stats), `web.log` viewer (`/api/weblog`), and remote reboot (`/api/reboot`), verified **12/12 PASS** with Gate 12 loopback & `0 B` SRAM delta.
- [x] **4.3 Pre-Compiled `.mpy` Core OS Bytecode & Desktop/Settings Polish (`picocalc.ps1`, `ui/`, `core/`):**
  - Automated `mpy-cross` (`v1.25.0`, mpy `v6.3`, `-O2`) build & deploy pipeline in `picocalc.ps1` for 31 core OS modules (`boards/`, `core/`, `ui/`, `net/`, `web/`, `tools/_shell_cmds.py`, `tests/`, and `main.py` → `_pinhos_main.mpy` + entry shim; `-NoMpy` fallback), reclaiming **+84 KB free SRAM (`~220–240 KB` free / `96 KB` contiguous block on boot)** while keeping `tools/*.py`, `apps/*.py`, `themes/*.json`, and `web/static/*` plain text on SD.
  - Upgraded Desktop Home (`ui/desktop.py`) with live **CPU sparkline**, horizontal **SWAP bar**, `WEB ON [6:KEY]` indicator, and `IP: X.X.X.X` / `Offline` status; added configurable **SD Swap Quota** (`swap_max_kb`) & eviction in `core/swap.py`.
  - Expanded Settings to **6 categories** (`ui/menu.py`, on-demand `ui/_menu_net.py`, `ui/_log_view.py`) with dedicated **Date, Time & NTP** (manual Date/Time editors, background-only NTP, persistent SD RTC retention in `/sd/pinhos/rtc_state.json`), **Wi-Fi Country Code** prompt & ISO-3166 alpha-2 validation (`wifi_country`), and `ListMenu` Log File Picker (`CTRL+L`).
- [x] **4.4 Stability, Security, Watchdog & Audit Close-Out (`v1.0.0-alpha.4.1` → `v1.0.0-alpha.4.2`):**
  - **WebPortal Read/Write Auth Hardening (`#23`):** Fail-closed 16-hex `os.urandom(8)` token (removed static fallback), `X-PinhOS-Token` enforced across all `/api/*` reads & writes, sensitive-file denylist (`wifi.json`, `.swap/`, `breadcrumb.json`, `boot_state.json`, `rtc_state.json` → `403`), 5-failure `429` lockout (`30s`), authenticated Blob URLs in `web/static/app.js`, and uncropped on-device `WEBPORTAL IDE ACTIVE` URL & Token popup (`[6]` menu).
  - **RP2350 Hardware Watchdog Coverage (`#14`, `#28`):** Shared `sys.modules["__pinhos_wdt__"]` handle (working around read-only MicroPython `builtins`), unconditional `feed_wdt()` in `ui_loop()` (with or without WebPortal active), automatic `board.poll_key` WDT-feed wrapper in `core/sandbox.py` for all sandboxed tools (`shell`, `files`, `editor`, etc.), `_TrackedHandle` file I/O feeds, `<= 4s` `net/sync.py` socket timeouts, standalone-only arming, and hardware `Timer` REPL keep-alive after serial `Ctrl+C`.
  - **Observability, Heap Telemetry & Autostart (`#13`, `#24`, `#26`, `#29`):** Cached per-boot `boot_id` + `+ms` timestamps, HTTP status/IP/denied request logs in `web.log`, Wi-Fi/NTP result logs, `largest_free(cap=98304)` 96 KB contiguous-heap probe, `HEAP[BOOT_OK|WEB_START|IDLE_DESKTOP|FIRST_TOOL]` timeline logs, and idempotent `_init_interactive_services()` on `ui_loop()` entry.
  - **Deep Stress Suite & Release Engineering (`#11`, `#21`, `#25`):** Dedicated `.\picocalc.ps1 stress` action (Gate 13 `20×` real-tool launch, Gate 14 live Wi-Fi scan + HTTP + pause/resume, 7-menu walk), UI auto-restore after `test`/`stress`, `scripts/stamp_release.ps1` + `.github/workflows/release-check.yml` tag validator, and runbooks/design docs (`docs/runbooks/`, `docs/design/phase5_ota_security.md`).

---

### Phase 5: Wi-Fi SoftAP Fallback, Signed Atomic OTA & App/Theme Store (`net/`)
- [ ] **5.1 Wi-Fi STA Manager, Async Background Radio & SoftAP Captive Fallback (`net/wifi.py`):**
  - [x] Multi-network credential store (`wifi.json`), signal strength scanner, 3-attempt auto-retry connect with hard CYW43 radio bounce, ISO-3166 `wifi_country` prompt, and literal-IPv4 UDP NTP + non-blocking HTTP Date fallback.
  - [ ] Move Wi-Fi association, DHCP polling, and NTP sync to a fully asynchronous `uasyncio` background task (with RP2350 Core 1 LCD DMA / CYW43439 concurrency tuning so networking never impacts UI responsiveness or drops UDP packets).
  - [x] **Configurable Boot & Periodic NTP Sync + RTC Persistence (`#47`, `#55`):** Automatically trigger non-blocking NTP sync immediately after boot Wi-Fi connects (when both `wifi_auto_connect` and `ntp_auto` are enabled in `config.json`), support configurable periodic background resync (`ntp_resync_s`), and persist synced RTC state to `/sd/pinhos/rtc_state.json` on sync, periodically (`rtc_save_interval_s = 300`), and before sleep/reboot.
  - [ ] Automatic SoftAP hotspot fallback (`PinhOS-Setup`) for headless field configuration via WebPortal when no saved STA network is reachable.
- [ ] **5.2 Signed Atomic GitHub OTA Updater (`net/ota.py` — per `docs/design/phase5_ota_security.md`):**
  - [x] Security & authenticity architecture design (`docs/design/phase5_ota_security.md`) + single-source-of-truth `version.json` OTA metadata (`#21`).
  - [ ] Execute on-device TLS heap spike benchmark (measure free SRAM & `largest_free(96KB)` during `ssl.wrap_socket` to GitHub raw/API).
  - [ ] Implement clean-heap **Updater Mode** (stop WebPortal, purge UI modules before TLS), download signed `release_manifest.json` + changed files into `/sd/pinhos/.ota_staging/`, verify signature/pinned release & SHA-256 digests, atomically swap A/B files (writing `version.json` last), and integrate with the 3-strike Boot Guard for automatic rollback.
- [ ] **5.3 GitHub App & Theme Store (`net/store.py`):**
  - [x] Direct GitHub theme/app sync and remote version check (`net/sync.py`).
  - [ ] Curated catalog browser (`store_index.json`) with category filters, version tags, `min_sram` compatibility badges, SHA-256 verification, and one-click install/update/remove into `/sd/pinhos/apps/` and `/sd/pinhos/themes/`.
- [ ] **5.4 Optional Bytecode & Diagnostics Polish:**
  - [x] Surface RP2350 Watchdog (`WDT`) diagnostics & reset-cause log entries (`wdt.log` + friendly `WATCHDOG RESET RECOVERED` notice) directly in the on-device **Logs** menu (`CTRL+L` / `ui/_log_view.py`, `v1.0.0-alpha.4.4`, `#48`).
  - [x] Implement **Extensible Theme Schema v2 & Selectable `6×8` Fonts (`#67`):** Deep-merged colors, widget chrome style tokens (`border_style`, `bar_style`, `card_header`, `quick_strip`), `uppercase_headers`, custom ASCII banners, compact `570 B` `6×8` bitmap fonts (`default`, `bold`, `retro`, `/sd/pinhos/fonts/*.bin`), and built-in **Obsidian Amber** theme (`v1.0.0-alpha.5.0`).
  - [x] Implement **Two-Stage Soft + Hard Watchdog (`#54`):** Periodic `machine.Timer` supervisor (with RP2350 alarm-pool `coop` fallback) keeping the 8s silicon WDT fed for true deadlocks while enforcing a configurable soft timeout (`15s`/`30s`/`60s`/`OFF`) with a Windows-style **"Not Responding"** dialog (`[W] Wait`, `[ESC] Abort`, `[R] Reboot`).
  - [x] Implement **MemGuard & SRAM Hardening (`v1.0.0-alpha.5.0`):** Idle & pre-flight stale-module/idle-WebPortal reclaimer (`core/memutil.py`), lazy GUI/TUI backends, zero-eager `__init__.py` packages, and moved 14 BusyBox FS command handlers from `tools/shell.py` into pre-compiled `tools/_shell_cmds.mpy` (`32.5 KB → 23.8 KB`).
  - [x] Standardize the `F1`–`F5` (`F1:Help`, `F2:Thm`, `F3:Mode`, `F4:Cfg`, `F5:Notes`) & `Shift+F6`–`F10` (`WEB`, `COM`, `Mouse` hook, `Notes Edit`, `Self-Test`) function-key bar with an `[F1]` Help popup on Desktop Home & App Drawer (`#64`, `#66`).
  - [x] Always render all 3 status rows (`IP`/`Offline`, `SIG` + `GUI`/`TUI`, and `WEB ON`/`WEB OFF`) in `DesktopHome` `SYS TELEMETRY` (`#56`).
  - [ ] Add on-device WebPortal QR code generator for quick phone/laptop URL + token pairing.
  - [ ] Add on-device **License & Legal Notices** viewer next to **About PinhOS** in Settings (`#58` — PolyForm Noncommercial 1.0.0, `NOTICE`, and third-party attributions streamed in `<= 1 KB` chunks).
  - [ ] Add configurable **Time Format** (`24h` / `12h` AM/PM) and **Date Format** (EU `DD/MM/YYYY` / US `MM/DD/YYYY` / ISO `YYYY-MM-DD`) settings across Desktop Home, StatusBar, and Date & Time UI (`#62`).

---

### Phase 6: Bluetooth 5.2 HID Host & Peripherals (`net/ble.py`)
- [ ] **6.1 BLE Central & Device Pairing:**
  - Utilize CYW43439 `ubluetooth` (NimBLE) to scan, pair, bond, and auto-reconnect with standard BLE HID peripherals (full-size keyboards, mini trackballs/mice, wireless barcode/RFID scanners).
- [ ] **6.2 Unified Input Multiplexer:**
  - Merge incoming BLE HID keycodes and relative pointer events into the `boards/` input queue so external wireless peripherals work transparently across GUI Mode, TUI Mode, Desktop Home, and all sandboxed apps.

---

## 4. Release `v1.1.0` — Power & Native Performance

### Phase 7: Multi-UF2 Chainloader & Dynamic C `.mpy` Engine
- [ ] **7.1 Multi-UF2 SD Card Chainloader:**
  - Scan `/sd/firmwares/*.uf2`, parse UF2 block headers, target flash offsets, and RP2350 architecture family IDs (`0xe48bff59` ARM Cortex-M33 vs `0xe48bff5a` RISC-V Hazard3).
  - Implement safe flash loader stub to boot bare-metal C firmwares (emulators, Doom, standalone RF/logic tools) directly from SD, returning cleanly to PinhOS on power-cycle.
- [ ] **7.2 Dynamic Native C Modules (`.mpy` / `py/dynruntime.h`):**
  - Establish cross-compilation toolchain and manifest schema (`"arch": "armv7emsp"`) for drop-in `.mpy` native binaries stored alongside Python app wrappers in `/sd/pinhos/apps/<app>/`.
  - Deliver reference C-accelerated MP3 audio decoder (`mp3dec.mpy` + `apps/mp3_player.py` driving `machine.I2S` DMA), fast FFT spectrum visualizer, and checksum/crypto primitives.

---

## 5. Release `v1.2.0` — Commercial Packaging & IP Protection

### Phase 8: Frozen Core Firmware, Hardware Licensing & Encrypted Pro Packs
- [ ] **8.1 Frozen `.mpy` Core Bytecode (`manifest.py`):**
  - Pre-compile proprietary `core/`, `ui/`, `boards/`, and commercial Pro applets via `mpy-cross` directly into a custom RP2350 `.uf2` firmware image.
  - Execute frozen bytecode directly from QSPI flash (XIP)—eliminating plain-text core source code from the FAT32 SD card while freeing significant SRAM heap.
- [ ] **8.2 RP2350 Hardware-Locked Licensing:**
  - Provision a read-locked cryptographic salt into RP2350 One-Time Programmable (OTP) fuses paired with RP2350 Secure Boot signature enforcement.
  - Validate signed `/sd/pinhos/license.key` files bound to the target chip's 64-bit `machine.unique_id()` (Ed25519 / HMAC-SHA256) to prevent SD card cloning and unauthorized `.uf2` redistribution.
- [ ] **8.3 Encrypted OTA Pro Field Packs:**
  - Package specialized commercial vertical suites (e.g., NetOps/NOC switch-port & VLAN audit pack, industrial Modbus/CAN diagnostics) as AES-encrypted `.mpy` bundles.
  - Decrypt licensed Pro modules strictly into volatile SRAM at runtime via `cryptolib` using keys derived from the RP2350 OTP secret + `unique_id()`, ensuring unencrypted bytecode never touches the SD card.

---

## 6. Release `v1.3.0` — Cloud WebPortal Relay & Persistent Identity

### Phase 9: Outbound WSS Cloud Portal, Persistent Auth & License Integration
- [ ] **9.0 Cloud Relay & Auth Protocol Spec (`docs/design/v1.3_cloud_wss.md`):**
  - Reference UX & ecosystem prototype: [`docs/portal-preview/pinhos_cloud_webportal_ecosystem_prototype.html`](docs/portal-preview/pinhos_cloud_webportal_ecosystem_prototype.html) (Product & Ecosystem landing, Cloud Studio IDE, Devices & Licensing / Pair New Device flow).
  - Lock down the WSS JSON/binary framing schema, HMAC/Ed25519 challenge-response handshake (never transmitting raw `device_key.json` secrets), server certificate/SPKI pinning strategy, and cloud relay backend architecture before firmware implementation.
- [ ] **9.1 Outbound WSS Relay Client (`net/wss_client.py`):**
  - Replace the local multi-socket HTTP portal (`0.0.0.0:8080`) during normal WAN-connected operation with a single persistent outbound TLS WebSocket (`wss://`) to the cloud-hosted WebPortal backend—enabling off-LAN remote access through CGNAT/hotspots without router port forwarding while reclaiming `~25 KB` of local HTTP/lwIP socket overhead.
  - Implement lightweight JSON-over-WSS control framing (`status`, `run`, `key`, `file`) paired with `1 KB` chunked binary WebSocket frames (`opcode 0x02`) for zero-Base64 `320x320` 4-bit BMP screenshot streaming, reusing a single pre-allocated `1024 B` `bytearray` buffer.
  - Manage RP2350 mbedTLS SRAM budget (`~30–40 KB` live TLS buffer) with **auto-pause/resume** during SRAM-heavy apps or OTA updates, 30s `PING/PONG` heartbeat, exponential backoff + jitter reconnect, and server certificate/SPKI pinning.
  - Retain a stripped-down local HTTP listener strictly for `PinhOS-Setup` SoftAP captive provisioning and an explicit offline `"Local LAN Mode"` toggle.
- [ ] **9.2 Persistent Device Identity, Pairing & Remote-Control Guard:**
  - Replace the ephemeral per-boot 16-hex `X-PinhOS-Token` UX with a persistent device identity bound to `machine.unique_id()` and a long-lived secret stored in `/sd/pinhos/device_key.json`.
  - Support one-time pairing via a short pairing code or on-device QR code so subsequent boots authenticate silently over `wss://` with zero manual token entry, plus an `"Unpair Cloud / Rotate Key"` action in Settings (`set_conn`).
  - Add an on-device **Remote-Control Safety Switch** (`Cloud: OFF / View-Only / Full Control`) paired with a visible **`CLD`** status badge so remote `run`/`key`/`file` commands can never execute silently without user awareness.
- [ ] **9.3 Cloud-Integrated Licensing & Entitlement Sync:**
  - Prepare and integrate the runtime license verification mechanism on WSS handshake (`machine.unique_id()` + signed HMAC/Ed25519 entitlement payload), validating `Free` vs `Pro` tier access and pushing signed `/sd/pinhos/license.key` updates or Pro Field Packs directly from the cloud backend.
  - Cache signed license/entitlement state locally with an offline grace window anchored to NTP/monotonic counters (preventing RTC clock-rollback abuse) so licensed tools continue operating seamlessly when off-grid.
  - Support cloud-side **Deactivate / Transfer Device** and signed revocation lists for hardware replacements or upgrades.
- [ ] **9.4 Encrypted Cloud Config & Workspace Backup (Pro Feature):**
  - Provide 1-click encrypted cloud backup and restore of `config.json`, custom JSON themes, Quick Notes, and user `apps/` over the authenticated WSS channel.
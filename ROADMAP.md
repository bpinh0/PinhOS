# PinhOS — Master Engineering Roadmap & Architecture Spec

* **Target Hardware:** ClockworkPi PicoCalc (Primary) & Portable Pico 2W / RP2350 Decks (Dual-Core Cortex-M33 @ 150 MHz, 520 KB SRAM, CYW43439 Wi-Fi + BLE 5.2, 16-Color RGB565 LUT Display)

* **Runtime:** MicroPython on RP2350 + Immutable Flash Bootloader (`/sd/pinhos/` live payload)

* **Versioning Schema:** SemVer 2.0.0 (`1.0.0-dev.<build>+<sha>`, `1.0.0-beta.<n>+<sha>`, `1.0.0-rc.<n>+<sha>`, `1.0.0`, `1.1.0`) tracked in `/sd/pinhos/version.json`

* **Visual & Theme Targets:** Match `docs/mockups/` (`ui_native_*.jpg` for `NATIVE` + `LIST`, `ui_lvgl_*.jpg` for `LVGL` + `MOSAIC`, `ui_desktop_mode.jpg` for Desktop Mode, `webportal_studio.jpg` for WebPortal) and `themes/*.json` schema.

## Target Directory Layout (`/sd/pinhos/`)

```
/sd/pinhos/
├── main.py                  # Boot guard, 3-strike safe-mode check & HOT_RELOAD loop
├── version.json             # SemVer metadata, build number, channel & changelog
├── config.json              # User preferences, Wi-Fi creds, active theme, F1-F10 map, BLE bonds
├── board_config.json        # Active hardware HAL profile ("picocalc" | "cardkb_ili9341" | "headless")
├── secrets.py               # Optional private tokens/credentials (gitignored)
├── crash.log                # Last BSOD stack trace & heap telemetry
├── .swap/                   # Cold buffer & state swap directory (gitignored)
├── .versions/               # Offline OTA snapshot backups for rollback (gitignored)
├── .boot_once               # Ephemeral chainloader handoff flag for v1.1.0 multi-UF2 boot (gitignored)
├── boards/
│   ├── __init__.py          # Lazy factory get_board() — loads only the active HAL profile into SRAM
│   ├── base.py              # BaseBoard contract (display, read_key, get_battery, backlight, sleep)
│   ├── picocalc.py          # ClockworkPi PicoCalc HAL (320×320 LCD, STM32 I2C keyboard & PMU)
│   └── cardkb_ili9341.py    # DIY Pico 2W + 320×240 SPI ILI9341 + M5Stack CardKB (I2C 0x5F) HAL
├── core/
│   ├── kernel.py            # State machine, atomic file I/O, BSOD handler, sleep/wake reset
│   ├── input.py             # Unified input router (Board HAL + WebPortal + BLE HID)
│   ├── swap.py              # Cooperative SD state spill & SwapPager (wear-safe)
│   ├── sandbox.py           # Isolated app namespace, sys.modules snapshot & gc cleanup
│   └── bridge.py            # <<PINHOS:...>> framed UART protocol over USB Serial
├── ui/
│   ├── renderer.py          # Dynamic W×H Native 16-color RGB565 LUT & dirty-rectangle redraws
│   ├── lvgl_backend.py  # Optional LVGL adapter with automatic fallback to NATIVE
│   ├── themes.py            # Unified JSON theme loader (LUT + LVGL styles + Web CSS)
│   └── desktop.py           # Optional desktop icon & taskbar workspace (dynamic W×H layout)
├── themes/                  # Starter JSON themes (black_forest, cyber_amber, phosphor_green...)
├── net/
│   ├── wifi.py              # Non-blocking Wi-Fi connect/retry & NTP clock sync
│   ├── ota.py               # GitHub Releases/Trees API updater & .versions/ rollback
│   └── ble.py               # BLE 5.2 HID over GATT (HOGP) central for keyboards, mice & gamepads
├── web/
│   └── server.py            # Non-blocking HTTP server, REST API & theme-synced WebPortal
├── apps/
│   ├── shell.py             # BusyBox shell (ping, scan, wol, nslookup, ifconfig, py)
│   ├── files.py             # File Commander (/sd), F5 info, Open With, .bmp screenshots
│   ├── store.py             # Git App Store & APP_META manifest inspector
│   ├── studio.py            # On-device & WebPortal App Studio sandbox runner
│   └── lab.py               # GPIO inspector, I2C scanner, PWM signal gen & RTC timer
└── tests/
    └── selftest.py          # Incremental on-device regression suite (grown across Phases 1–7)

/sd/firmwares/               # Standalone bare-metal .uf2/.bin payloads for v1.1.0 chainloader (Doom, emulators...)

```

## v1.0.0 Release Milestones (Phases 1–6)

### Phase 1: Modular Refactor, Hardware HAL, 6-Domain Main Deck, Core Fixes & Test Harness

**Goal:** Break monolithic `pinhos_os.py` into `/sd/pinhos/`, introduce `boards/` HAL + `version.json`, clean up legacy branding, fix all core runtime bugs, and establish the automated regression gate.

* \[ \] **Modularize Codebase:** Refactor `pinhos_os.py` into `main.py`, `boards/`, `core/`, `ui/`, `net/`, and `apps/`. Replace legacy `Plugins` terminology with `Apps` (`APP_META`).

* \[ \] **Lightweight Hardware Abstraction Layer (`boards/` & `board_config.json`):**

  * Implement `boards/base.py` (`BaseBoard`) and lazy factory `boards/__init__.py` (`get_board()`) so only the active hardware profile is imported into SRAM.

  * Implement `boards/picocalc.py` (default `320×320` PicoCalc display, STM32 I2C keyboard & PMU telemetry) alongside `boards/cardkb_ili9341.py` (`320×240` SPI TFT + I2C `0x5F` CardKB + `VSYS` ADC) and `headless` profile support.

  * Enforce dynamic screen geometry (`W = board.WIDTH`, `H = board.HEIGHT`, dynamic `visible_rows` calculation) across `ui/renderer.py` and `ui/desktop.py` instead of hardcoding `320×320`.

* \[ \] **Scrub Personal Strings & Set Defaults:** Remove personal/author names from default UI banners/boot screens; default `git_repo` to `"PinhOS/PinhOS"`.

* \[ \] **Version Metadata (`version.json`):** Initialize `/sd/pinhos/version.json` at `1.0.0-dev.19` and add **About & Version Info** under `System, Network & OTA`.

* \[ \] **6-Domain Main Deck:**

  1. `1. DASHBOARD & TELEMETRY [F1]`

  2. `2. APPS & STUDIO [APPS >]`

  3. `3. TERMINAL & TOOLKIT [SH >]`

  4. `4. FILE COMMANDER [/sd >]`

  5. `5. HARDWARE & LAB [LAB >]`

  6. `6. SYSTEM, NET & OTA [SYS >]`

* \[ \] **Phase 1 Bug Fixes:**

  * **Sleep / Wake State Reset:** Entering Sleep or Shutdown must reset the active UI route/cursor back to the default home screen (Main Deck or Desktop Workspace if enabled) so waking up never drops the user back inside the Settings/Power submenu.

  * Idle 1-second dirty-rectangle header tick (clock + RAM/battery telemetry without full-screen flicker).

  * Active `LNK` status badge + `F4` toggle for serial/WebPortal link state.

  * NTP sync error handling -> graceful log/BSOD + `crash.log` without hard lockup.

  * Display real LAN IP (`wlan.ifconfig()[0]`) on Dashboard instead of placeholder/loopback.

  * BusyBox TCP `ping` (RTT ms) + ICMP/discovery toggle.

  * Clean `HOT_RELOAD` teardown loop in `main.py` (deinit sockets/timers before reload).

  * Forced `TEST_AUTH` modal verification for WebPortal PIN/token auth.

* \[ \] **Deployment & Test CLI (`picocalc.ps1`):**

  * Replace hardcoded `COM4` with automatic Raspberry Pi USB VID (`2E8A`) port discovery, optional `-Port COMx` override, and pre-flight serial port lock/busy detection (reporting a clear error if Thonny, PuTTY, or another monitor holds the port).

  * Update `upload_and_start` to recursively sync `/sd/pinhos/` (excluding `.git/`, `docs/`, `tests/`, `README.md`, `ROADMAP.md`, `LICENSE`) with active theme colors on the progress bar.

  * Add `.\picocalc.ps1 test` to push and execute `/sd/pinhos/tests/selftest.py` over serial and report pass/fail telemetry.

* \[ \] **Phase 1 Self-Test Foundation (`tests/selftest.py`):**

  * Build the lightweight on-device test runner and initial Phase 1 checks: `boards/` HAL contract & dynamic `W×H` geometry validation, `gc.mem_free()` sandbox leak verification (`core/sandbox.py`), `.swap/` round-trip spill/cleanup (`core/swap.py`), synthetic input & Sleep/Wake home reset verification (`core/input.py`), non-blocking NTP failure logging, and non-destructive I2C PMU/keyboard ACK + ADC battery bounds check.

### Phase 2: GitHub OTA Updater, Instant Rollback & Immutable Bootloader

**Goal:** Enable self-updating over Wi-Fi with zero-brick recovery.

* \[ \] **GitHub OTA (`net/ota.py`):** Query GitHub Releases/Trees APIs filtered by SemVer channel (`STABLE`, `BETA`, `DEV`), verify SHA hashes so only changed files are fetched, stream-download to staging, and atomically swap into `/sd/pinhos/`.

* \[ \] **Offline `.versions/` Snapshots:** Archive prior working `/sd/pinhos/` builds into `/sd/pinhos/.versions/<ver>/` (retaining last 2) for 1-click offline rollback.

* \[ \] **Immutable Flash Bootloader (`tools/build_boot_uf2.sh` & `tools/setup_persistent_boot.py`):** Flash-resident `boot.py`/`main.py` stub that mounts `/sd`, checks 3-strike boot failure counter, and boots `/sd/pinhos/main.py` (or enters Safe Mode recovery shell).

* \[ \] **Phase 2 Regression Hook (`tests/selftest.py`):** Append `test_ota_and_rollback()` to validate `version.json` SemVer parsing and `.versions/` snapshot/rollback dry-runs.

### Phase 3: Theme-Synced WebPortal, App Studio & File Associations

**Goal:** Full browser-based control, live code execution, and file associations.

* \[ \] **Theme-Synced WebPortal (`web/server.py` & `portal.html`):** Inject active `themes/*.json` colors into `:root` CSS variables; provide real-time `<canvas>` screen mirror (matching `board.WIDTH × board.HEIGHT`), virtual D-Pad/`F1`–`F10` input, and SD file manager (matching `docs/mockups/webportal_studio.jpg`).

* \[ \] **App Developer Studio (`apps/studio.py`):** Browser + on-device Python editor, drag-and-drop upload, `dev_watch.ps1` USB hot-push, and isolated sandbox runner (`core/sandbox.py`) with live console streaming.

* \[ \] **Scratchpad Notes:** Lightweight Markdown/text notes synced between PicoCalc and WebPortal.

* \[ \] **File Commander Enhancements (`apps/files.py`):** `F5` file/metadata inspector, custom extension-to-app associations (`APP_META["ext"]` + `Open With...`), `F10`/`Ctrl+P` `.bmp` framebuffer screenshots, and storage analyzer.

* \[ \] **Phase 3 Regression Hook (`tests/selftest.py`):** Append `test_webportal_auth_and_studio()` to verify `TEST_AUTH` PIN/token rejection vs. acceptance and sandboxed Studio execution.

### Phase 4: Dual-Backend Graphics (`NATIVE` + `LVGL`), Theme Engine & Desktop Mode

**Goal:** Support both ultra-fast 16-color LUT and smooth LVGL rendering from a single JSON theme system.

* \[ \] **Unified Theme Engine (`ui/themes.py`):** Parse `themes/*.json` (`id`, `name`, `layout`, `font_scale`, `lvgl.*`, 12 semantic `colors.*`) into Native 16-color RGB565 LUTs, LVGL `lv.style_t` styles, and WebPortal CSS tokens. Sync `/themes` from GitHub.

* \[ \] **Cooperative SD Swap (`core/swap.py`):** Spill cold logs, terminal scrollback, and store caches to `/sd/pinhos/.swap/` before initializing LVGL or launching heavy apps.

* \[ \] **Optional LVGL Backend (`ui/lvgl_backend.py`):** Render `MOSAIC` 6-card grid and anti-aliased widgets when `ui_backend == "LVGL"`, automatically falling back to `NATIVE` if `lvgl` module is absent or free SRAM is below threshold.

* \[ \] **Optional Desktop Mode (`ui/desktop.py`):** Icon workspace (`Term`, `Files`, `Studio`, `Lab`, `MP3`, `Notes`), floating telemetry/notes widgets, and bottom taskbar (`[PINHOS]` launcher, active app indicator, clock/telemetry) toggleable as the default home screen (also respected on Sleep/Wake reset), configurable `F1`–`F10` multi-page hotkeys, and idle screensaver.

* \[ \] **Phase 4 Regression Hook (`tests/selftest.py`):** Append `test_themes_and_ui_fallback()` to compile all `themes/*.json` presets into RGB565 LUTs/CSS tokens and verify graceful `LVGL -> NATIVE` fallback under low SRAM.

### Phase 5: Cyberdeck Field Toolkit & Hardware Lab

**Goal:** Turn PicoCalc into a standalone network and hardware diagnostic tool.

* \[ \] **BusyBox Network Suite (`apps/shell.py`):** Non-blocking TCP port scanner (`scan`), Wake-on-LAN magic packet sender (`wol`), `nslookup`, `ifconfig`, `dmesg`, and `py` REPL evaluator.

* \[ \] **Serial UART Console (`minicom` mode):** Interactive UART terminal over exposed `UART0`/`UART1` pins (`9600`–`921600` baud) with `/sd` session logging.

* \[ \] **Hardware & Diagnostics Lab (`apps/lab.py`):** Live GPIO/Pinout inspector (`IN`/`OUT`/`ADC`), I2C bus scanner, PWM / square-wave signal generator (`1 Hz`–`100 kHz`), crash forensics viewer, and background RTC Pomodoro/Alarm timer.

* \[ \] **USB / SD Transfer Bridge:** Expose `/sd` over USB Mass Storage (when supported by firmware) or high-speed WebPortal transfer.

* \[ \] **Phase 5 Regression Hook (`tests/selftest.py`):** Append `test_toolkit_and_lab()` to verify BusyBox TCP `ping`/port scan non-blocking timeouts and PWM/GPIO state cleanup.

### Phase 6: Bluetooth BLE 5.2 Peripheral Support

**Goal:** Pair wireless keyboards, mice, and gamepads directly to the Pico 2W's CYW43439 chip without starving SRAM or Wi-Fi.

* \[ \] **Unified Input Router (`core/input.py`):** Consolidate keystrokes and pointer deltas from the active `boards/` HAL, WebPortal virtual input, and BLE HID devices into a single event queue.

* \[ \] **BLE HID Central (`net/ble.py`):** Scan, pair, and bond with BLE HID over GATT (HOGP) keyboards, mice (driving the Desktop Mode cursor), and gamepads using `ubluetooth`/`aioble`, persisting bonded MAC addresses and LTK keys in `config.json`.

* \[ \] **Radio & SRAM Coexistence Mode:** Add `Bluetooth & Peripherals` under `System, Network & OTA`, a top-bar `BT` status badge alongside `Wi-Fi` and `LNK`, and an optional **Radio Exclusive / Swap** toggle that spills cold buffers via `core/swap.py` when BLE and Wi-Fi run concurrently.

* \[ \] **Phase 6 Regression Hook (`tests/selftest.py`):** Append `test_ble_hid_coexistence()` to verify BLE HID report injection into `core/input.py` and SRAM swap stability alongside Wi-Fi.

## v1.1.0 Roadmap (Post-Release Expansion)

### Phase 7: Multi-UF2 Chainloader & Native `.mpy` Engine (`v1.1.0`)

**Goal:** Launch standalone bare-metal PicoCalc `.uf2`/`.bin` firmwares (such as Doom, retro emulators, or Forth) and compiled C `.mpy` modules directly from PinhOS without overwriting the OS or losing user data.

* \[ \] **Protected 3-Slot Flash Layout & Boot Chainloader:**

  * **Slot 0 (`0x10000000`):** Protected C chainloader bootloader.

  * **Slot 1 (`0x10020000`):** PinhOS MicroPython runtime.

  * **Slot 2 (`0x10200000+`):** Ephemeral payload slot for external `.uf2`/`.bin` images.

* \[ \] **`/sd/firmwares/` Launcher & `.boot_once` Handoff:** Browse standalone PicoCalc payloads inside PinhOS, validate `.uf2` target address safety & CRC32 (avoiding redundant flash writes when re-launching the same payload), write `/sd/pinhos/.boot_once`, and reboot into Slot 2. Power-cycling or pressing Reset automatically clears `.boot_once` and returns cleanly to PinhOS.

* \[ \] **Native C Dynamic Modules (`.mpy`):** Support loading `armv7emsp` compiled `.mpy` game/DSP engines inside `/sd/pinhos/apps/` that render directly into `board.display` and exit cleanly back to PinhOS on `ESC`.

* \[ \] **Phase 7 Regression Hook (`tests/selftest.py`):** Append `test_chainloader_manifest_and_mpy()` to verify `.uf2` header/offset safety checks and `.boot_once` atomic cleanup.
# PinhOS — Master Engineering Roadmap & Architecture Spec

- **Target Hardware:** ClockworkPi PicoCalc (Raspberry Pi Pico 2W / RP2350, Dual-Core Cortex-M33 @ 150 MHz, 520 KB SRAM, CYW43439 Wi-Fi + BLE 5.2, 320×320 16-Color RGB565 LUT Display)
- **Runtime:** MicroPython on RP2350 + Immutable Flash Bootloader (`/sd/pinhos/` live payload)
- **Versioning Schema:** SemVer 2.0.0 (`1.0.0-dev.<build>+<sha>`, `1.0.0-beta.<n>+<sha>`, `1.0.0-rc.<n>+<sha>`, `1.0.0`) tracked in `/sd/pinhos/version.json`
- **Visual & Theme Targets:** Match `docs/mockups/` (`ui_native_*.jpg` for `NATIVE` + `LIST`, `ui_lvgl_*.jpg` for `LVGL` + `MOSAIC`, `ui_desktop_mode.jpg` & `ui_desktop_black_forest.jpg` for Desktop Mode, `webportal_studio.jpg` for WebPortal) and `themes/*.json` schema.

---

## Target Directory Layout (`/sd/pinhos/`)

```text
/sd/pinhos/
├── main.py                  # Boot guard, 3-strike safe-mode check & HOT_RELOAD loop
├── version.json             # SemVer metadata, build number, channel & changelog
├── config.json              # User preferences, Wi-Fi creds, active theme, F1-F10 map, BLE bonds
├── secrets.py               # Optional private tokens/credentials (gitignored)
├── crash.log                # Last BSOD stack trace & heap telemetry
├── .swap/                   # Cold buffer & state swap directory (gitignored)
├── .versions/               # Offline OTA snapshot backups for rollback (gitignored)
├── core/
│   ├── kernel.py            # State machine, atomic file I/O, BSOD handler, sleep/wake reset
│   ├── input.py             # Unified input router (PicoCalc matrix + WebPortal + BLE HID)
│   ├── swap.py              # Cooperative SD state spill & SwapPager (wear-safe)
│   ├── sandbox.py           # Isolated app namespace, sys.modules snapshot & gc cleanup
│   └── bridge.py            # <<PINHOS:...>> framed UART protocol over USB Serial
├── ui/
│   ├── renderer.py          # Native 16-color RGB565 LUT & dirty-rectangle redraws
│   ├── lvgl_backend.py      # Optional LVGL adapter with automatic fallback to NATIVE
│   ├── themes.py            # Unified JSON theme loader (LUT + LVGL styles + Web CSS)
│   └── desktop.py           # Optional desktop icon & taskbar workspace
├── themes/                  # Starter JSON themes (black_forest, cyber_amber, phosphor_green...)
├── net/
│   ├── wifi.py              # Non-blocking Wi-Fi connect/retry & NTP clock sync
│   ├── ota.py               # GitHub Releases/Trees API updater & .versions/ rollback
│   └── ble.py               # BLE 5.2 HID over GATT (HOGP) central for keyboards, mice & gamepads
├── web/
│   └── server.py            # Non-blocking HTTP server, REST API & theme-synced WebPortal
└── apps/
    ├── shell.py             # BusyBox shell (ping, scan, wol, nslookup, ifconfig, py)
    ├── files.py             # File Commander (/sd), F5 info, Open With, .bmp screenshots
    ├── store.py             # Git App Store & APP_META manifest inspector
    ├── studio.py            # On-device & WebPortal App Studio sandbox runner
    └── lab.py               # GPIO inspector, I2C scanner, PWM signal gen & RTC timer
```

---

## Phase 1: Modular Refactor, 6-Domain Main Deck & Core Bug Fixes
**Goal:** Break monolithic `pinhos_os.py` into `/sd/pinhos/`, introduce `version.json`, clean up legacy branding, and fix all core runtime bugs.

- [ ] **Modularize Codebase:** Refactor `pinhos_os.py` into `main.py`, `core/`, `ui/`, `net/`, and `apps/`. Replace legacy `Plugins` terminology with `Apps` (`APP_META`).
- [ ] **Scrub Personal Strings & Set Defaults:** Remove personal/author names from default UI banners/boot screens; default `git_repo` to `"PinhOS/PinhOS"`.
- [ ] **Version Metadata (`version.json`):** Initialize `/sd/pinhos/version.json` at `1.0.0-dev.19` and add **About & Version Info** under `System, Network & OTA`.
- [ ] **6-Domain Main Deck:**
  1. `1. DASHBOARD & TELEMETRY [F1]`
  2. `2. APPS & STUDIO [APPS >]`
  3. `3. TERMINAL & TOOLKIT [SH >]`
  4. `4. FILE COMMANDER [/sd >]`
  5. `5. HARDWARE & LAB [LAB >]`
  6. `6. SYSTEM, NET & OTA [SYS >]`
- [ ] **Phase 1 Bug Fixes:**
  - **Sleep / Wake State Reset:** Entering Sleep or Shutdown must reset the active UI route/cursor back to the default home screen (Main Deck or Desktop Workspace if enabled) so waking up never drops the user back inside the Settings/Power submenu.
  - Idle 1-second dirty-rectangle header tick (clock + RAM/battery telemetry without full-screen flicker).
  - Active `LNK` status badge + `F4` toggle for serial/WebPortal link state.
  - NTP sync error handling -> graceful log/BSOD + `crash.log` without hard lockup.
  - Display real LAN IP (`wlan.ifconfig()[0]`) on Dashboard instead of placeholder/loopback.
  - BusyBox TCP `ping` (RTT ms) + ICMP/discovery toggle.
  - Clean `HOT_RELOAD` teardown loop in `main.py` (deinit sockets/timers before reload).
  - Forced `TEST_AUTH` modal verification for WebPortal PIN/token auth.
- [ ] **Deployment Script (`picocalc.ps1`):**
  - Replace hardcoded `COM4` with automatic Raspberry Pi USB VID (`2E8A`) port discovery, optional `-Port COMx` override, and pre-flight serial port lock/busy detection (reporting a clear error if Thonny, PuTTY, or another monitor holds the port).
  - Update `upload_and_start` to recursively sync `/sd/pinhos/` (excluding `.git/`, `docs/`, `README.md`, `ROADMAP.md`, `LICENSE`) with active theme colors on the progress bar.

---

## Phase 2: GitHub OTA Updater, Instant Rollback & Immutable Bootloader
**Goal:** Enable self-updating over Wi-Fi with zero-brick recovery.

- [ ] **GitHub OTA (`net/ota.py`):** Query GitHub Releases/Trees APIs filtered by SemVer channel (`STABLE`, `BETA`, `DEV`), verify SHA hashes so only changed files are fetched, stream-download to staging, and atomically swap into `/sd/pinhos/`.
- [ ] **Offline `.versions/` Snapshots:** Archive prior working `/sd/pinhos/` builds into `/sd/pinhos/.versions/<ver>/` (retaining last 2) for 1-click offline rollback.
- [ ] **Immutable Flash Bootloader (`tools/build_boot_uf2.sh` & `tools/setup_persistent_boot.py`):** Flash-resident `boot.py`/`main.py` stub that mounts `/sd`, checks 3-strike boot failure counter, and boots `/sd/pinhos/main.py` (or enters Safe Mode recovery shell).

---

## Phase 3: Theme-Synced WebPortal, App Studio & File Associations
**Goal:** Full browser-based control, live code execution, and file associations.

- [ ] **Theme-Synced WebPortal (`web/server.py` & `portal.html`):** Inject active `themes/*.json` colors into `:root` CSS variables; provide real-time 320×320 `<canvas>` screen mirror, virtual D-Pad/`F1`–`F10` input, and SD file manager (matching `docs/mockups/webportal_studio.jpg`).
- [ ] **App Developer Studio (`apps/studio.py`):** Browser + on-device Python editor, drag-and-drop upload, `dev_watch.ps1` USB hot-push, and isolated sandbox runner (`core/sandbox.py`) with live console streaming.
- [ ] **Scratchpad Notes:** Lightweight Markdown/text notes synced between PicoCalc and WebPortal.
- [ ] **File Commander Enhancements (`apps/files.py`):** `F5` file/metadata inspector, custom extension-to-app associations (`APP_META["ext"]` + `Open With...`), `F10`/`Ctrl+P` `.bmp` framebuffer screenshots, and storage analyzer.

---

## Phase 4: Dual-Backend Graphics (`NATIVE` + `LVGL`), Theme Engine & Desktop Mode
**Goal:** Support both ultra-fast 16-color LUT and smooth LVGL rendering from a single JSON theme system.

- [ ] **Unified Theme Engine (`ui/themes.py`):** Parse `themes/*.json` (`id`, `name`, `layout`, `font_scale`, `lvgl.*`, 12 semantic `colors.*`) into Native 16-color RGB565 LUTs, LVGL `lv.style_t` styles, and WebPortal CSS tokens. Sync `/themes` from GitHub.
- [ ] **Cooperative SD Swap (`core/swap.py`):** Spill cold logs, terminal scrollback, and store caches to `/sd/pinhos/.swap/` before initializing LVGL or launching heavy apps.
- [ ] **Optional LVGL Backend (`ui/lvgl_backend.py`):** Render `MOSAIC` 6-card grid and anti-aliased widgets when `ui_backend == "LVGL"`, automatically falling back to `NATIVE` if `lvgl` module is absent or free SRAM is below threshold.
- [ ] **Optional Desktop Mode (`ui/desktop.py`):** Icon workspace (`Term`, `Files`, `Studio`, `Lab`, `MP3`, `Notes`), floating telemetry/notes widgets, and bottom taskbar (`[PINHOS]` launcher, active app indicator, clock/telemetry) toggleable as the default home screen (also respected on Sleep/Wake reset), configurable `F1`–`F10` multi-page hotkeys, and idle screensaver.

---

## Phase 5: Cyberdeck Field Toolkit & Hardware Lab
**Goal:** Turn PicoCalc into a standalone network and hardware diagnostic tool.

- [ ] **BusyBox Network Suite (`apps/shell.py`):** Non-blocking TCP port scanner (`scan`), Wake-on-LAN magic packet sender (`wol`), `nslookup`, `ifconfig`, `dmesg`, and `py` REPL evaluator.
- [ ] **Serial UART Console (`minicom` mode):** Interactive UART terminal over exposed `UART0`/`UART1` pins (`9600`–`921600` baud) with `/sd` session logging.
- [ ] **Hardware & Diagnostics Lab (`apps/lab.py`):** Live GPIO/Pinout inspector (`IN`/`OUT`/`ADC`), I2C bus scanner, PWM / square-wave signal generator (`1 Hz`–`100 kHz`), crash forensics viewer, and background RTC Pomodoro/Alarm timer.
- [ ] **USB / SD Transfer Bridge:** Expose `/sd` over USB Mass Storage (when supported by firmware) or high-speed WebPortal transfer.

---

## Phase 6: Bluetooth BLE 5.2 Peripheral Support
**Goal:** Pair wireless keyboards, mice, and gamepads directly to the Pico 2W's CYW43439 chip without starving SRAM or Wi-Fi.

- [ ] **Unified Input Router (`core/input.py`):** Consolidate keystrokes and pointer deltas from the built-in PicoCalc QWERTY matrix, WebPortal virtual input, and BLE HID devices into a single event queue.
- [ ] **BLE HID Central (`net/ble.py`):** Scan, pair, and bond with BLE HID over GATT (HOGP) keyboards, mice (driving the Desktop Mode cursor), and gamepads using `ubluetooth`/`aioble`, persisting bonded MAC addresses and LTK keys in `config.json`.
- [ ] **Radio & SRAM Coexistence Mode:** Add `Bluetooth & Peripherals` under `System, Network & OTA`, a top-bar `BT` status badge alongside `Wi-Fi` and `LNK`, and an optional **Radio Exclusive / Swap** toggle that spills cold buffers via `core/swap.py` when BLE and Wi-Fi run concurrently.
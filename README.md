# 🌲 PinhOS

**A modular, dual-UI MicroPython operating system and portable field cyberdeck platform for the ClockworkPi PicoCalc & Raspberry Pi Pico 2W (RP2350).**

> 🚀 **Status: `v1.0.0-alpha.4.2` — Phase 1, Phase 2, Phase 3, Phase 3.1 & Phase 4.x (WebPortal IDE, Security, Watchdog & Stability Audit Close-Out) Complete & Verified 12/12 + Deep Stress Suite (Gates 13–14 + Menu Walk) on Hardware.** Hardware Abstraction (`boards/`), 3-Strike Boot Guard & BSOD (`main.py`), RP2350 Hardware Watchdog with sandbox/tool/REPL keep-alive (`core/sandbox.py`, `main.py`), Sandboxed App Runner (`core/sandbox.py`), Quota-Managed Cooperative Swap (`core/swap.py`), Unified Theme Engine (`core/theme.py` + 4 JSON themes), Dual-UI Engine (`ui/` Android-style Desktop Home Screen with live SRAM/CPU sparklines, SWAP & Battery bars, `IP`/`Offline` status, `WEB ON [6:KEY]` & `<= 1 KB` Quick Notes ↔ 3×2 GUI Mosaic / TUI List App Drawer + 6-Category Hierarchical Settings Tree including Date/Time/NTP, Wi-Fi Country Code prompt & SD Swap Quota with `0 B` SRAM delta), Built-In BusyBox CLI (`tools/shell.py`), On-Device Text Editor (`tools/editor.py`), File Commander (`tools/files.py`), Network Probes (`tools/net_tools.py`), HAL-Routed UART1 Console (`tools/uart_term.py`), System Monitor & SD Benchmark (`tools/sysmon.py`), Hardened Non-Blocking `uasyncio` **WebPortal Browser IDE** (`web/server.py` with fail-closed 16-hex `X-PinhOS-Token` auth on all `/api/*` reads/writes, sensitive-file denylist, 5-fail `429` lockout, CORS/Origin guard & zero-dependency cyber-amber SPA under `web/static/`), CYW43439 RX-pumped Wi-Fi STA/Background NTP + persistent SD RTC retention (`net/wifi.py`, `core/config.py`), GitHub Sync (`net/sync.py`), Pre-Compiled `.mpy` Core OS Bytecode Deployment (`picocalc.ps1` via `mpy-cross -O2`, 31 `.mpy` modules, `~220–240 KB` free SRAM / `96 KB` contiguous block on boot), 4-Bit Indexed BMP Screenshots (`CTRL+P`), 12/12 On-Device Self-Test Gate + Deep Stress Suite (`tests/selftest*.py`), Release Stamping & CI Tag Verification (`scripts/stamp_release.ps1`, `.github/workflows/release-check.yml`), and Custom RP2350 Auto-Boot UF2 (`firmware/`) are all complete and verified on the ClockworkPi PicoCalc (Pico 2W). **Phase 5 (Async Background Wi-Fi/SoftAP, Signed Atomic SHA-256 OTA & App Store) is next.**

---

## Overview

PinhOS turns the ClockworkPi PicoCalc (and custom RP2350 hardware builds) into a fast-booting, deterministic pocket workstation and hardware/network field multitool. Built around a **95% MicroPython / 5% C & Viper** hybrid architecture, it balances instant on-device scripting and over-the-air updates with hardware-accelerated rendering, strict 520 KB SRAM management, and future commercial packaging support.

### Core Capabilities
* **Hardware Abstraction Layer (`boards/`):** Decouples core OS services from hardware pinouts and bus topologies—supporting the ClockworkPi PicoCalc (SPI LCD + I2C STM32 southbridge keyboard/battery + SPI SD) alongside custom Pico 2W + SPI/CardKB cyberdecks, with future portability to ESP32-S3.
* **Resilient Kernel Runtime (`core/`):**
  * **3-Strike Boot Guard & BSOD (`main.py`):** Persistent boot-strike counter with automatic Safe Recovery Mode fallback, unhandled-exception **Blue Screen of Death (`show_bsod()`)** with 1-key recovery, and `[ALT+F5]` Hard Reload (`x2` emergency hardware reset).
  * **Crash Forensics & On-Device Log Viewer (`core/logger.py` & `ui/_log_view.py`):** Rotating `/sd/pinhos/logs/system.log`, `crash.log`, and `web.log`, `breadcrumb.json` + `machine.reset_cause()` freeze detection, and a `[CTRL+L]` `ListMenu` log file picker right on the PicoCalc.
  * **Sandboxed App Execution (`core/sandbox.py`):** Enforces a single `APP_META` / `main(ctx)` contract, snapshots `sys.modules` and `gc.mem_free()` prior to launch, closes leaked file/socket descriptors on exit, purges app modules, and forces garbage collection (`< 2 KB` SRAM delta).
  * **Quota-Managed Cooperative Swap (`core/swap.py`):** Serializes inactive task state to `/sd/pinhos/.swap/` with configurable SD Swap Quota (`swap_max_kb`), oldest-file eviction, and a live Desktop Home SWAP bar to preserve heap headroom inside the RP2350's 520 KB SRAM ceiling.
  * **Pre-Compiled `.mpy` Core OS Bytecode (`picocalc.ps1`):** Automatically cross-compiles core OS modules (`boards/`, `core/`, `ui/`, `net/`, `web/`, `tools/_shell_cmds.py`, `tests/`, and `main.py` → `_pinhos_main.mpy` + entry shim) via `mpy-cross -O2` (`mpy v6.3`), eliminating on-device AST compiler SRAM spikes (~218 KB free SRAM on boot) while keeping `.py` sources clean in Git and `apps/`/`tools/`/`themes/` live-editable on SD.
* **Dual-UI Engine (`ui/`):**
  * **Shared Widget & Focus Model (`ui/widgets.py`):** Dirty-tracked `StatusBar`, `FooterBar`, `Panel`, `MosaicGrid`, `TelemetryStrip`, `ListMenu` (2-row partial redraws), `ProgressBar`, `Dialog`, and `TextView` sized for the PicoCalc's 6×8 display font (`53` chars × 320px) with zero full-screen Python framebuffers.
  * **GUI Mode (`ui/gui.py`) & TUI Mode (`ui/tui.py`):** Live `[TAB]`/`[CTRL+M]` switching between 320×320 framed graphical cards and high-density terminal layouts with `config.json` persistence and `0 B` SRAM delta, plus `[CTRL+P]` 4-bit indexed BMP screen capture to `/sd/pinhos/screenshots/`.
* **Unified JSON Theme Engine (`core/theme.py` & `themes/`):** Single JSON palette specification (`cyber_amber`, `phosphor_green`, `arctic_daylight`, `synthwave_pulse`) compiled to Core 1-safe in-place 16-entry RGB565 LUTs with live `[CTRL+T]` hot-swapping and safe built-in fallback.
* **WebPortal Browser IDE (`web/` — Phase 4.x):** Non-blocking `uasyncio` HTTP/REST server over Wi-Fi (`WEB` badge, `WEB ON [6:KEY]` desktop indicator, auto-start on boot, sleep suppression, CYW43 RX pump) secured with fail-closed 16-hex `X-PinhOS-Token` authentication across all `/api/*` reads & writes, sensitive-file denylist (`wifi.json`, `.swap/`, state files → `403`), 5-failure `429` lockout, and strict `Origin` / path-traversal checks. Serves a zero-dependency cyber-amber Browser IDE with live 320×320 screen capture, Virtual Controller (`/api/key`), SD file explorer, code/theme editor with syntax check & remote app launch, `web.log` viewer, and remote reboot.
* **Connectivity, Background NTP & Persistent RTC (`net/` & `core/config.py`):** Multi-SSID Wi-Fi STA manager with 3-attempt auto-retry + CYW43 RX FIFO pumping (`0%` ping loss), non-blocking background NTP sync + manual Date/Time config with SD RTC retention (`/sd/pinhos/rtc_state.json`), and direct GitHub theme/app/version sync (`net/sync.py`), expanding in Phases 5–6 to async background Wi-Fi/SoftAP captive setup, SHA-256 verified OTA updates, and BLE 5.2 HID peripheral support.
* **Built-In Field Tooling (`tools/`):** Interactive BusyBox-style CLI shell (`shell.py` + `_shell_cmds.py`), on-device text/JSON editor (`editor.py`), SD & flash file commander (`files.py`), DNS/TCP/subnet/WoL network probes (`net_tools.py`), HAL-routed `UART1` serial console (`uart_term.py`), and live SRAM/CPU/SD benchmark monitor (`sysmon.py`).

---

## Release Roadmap

| Version | Milestone | Focus & Deliverables |
| :--- | :--- | :--- |
| **`v1.0.0`** | **Foundation & Daily Driver** *(Active)* | `boards/` HAL (PicoCalc & custom SPI/CardKB decks), 3-strike boot guard, sandboxed app runner & `.swap/`, GUI/TUI dual-UI + Desktop Home (`v1.0.0-alpha.3.1`), unified JSON theme engine, BusyBox/net/UART field tools (`v1.0.0-alpha.3`), WebPortal browser IDE, GitHub OTA/App Store, and BLE 5.2 HID host. |
| **`v1.1.0`** | **Power & Native Performance** | Multi-UF2 SD card chainloader (supporting both RP2350 ARM Cortex-M33 and RISC-V Hazard3 `.uf2` images) and dynamic C `.mpy` native modules (`py/dynruntime.h`) for real-time MP3 audio decoding, DSP, and fast framebuffer blits. |
| **`v1.2.0`** | **Commercial Packaging & IP Protection** | Frozen `.mpy` core bytecode compiled into signed RP2350 `.uf2` firmware (flash XIP execution), RP2350 OTP + Secure Boot + `machine.unique_id()` node-locked licensing, and AES-encrypted OTA Pro Field Packs decrypted strictly in SRAM. |

See [`ROADMAP.md`](./ROADMAP.md) for the full technical architecture, contracts, memory budgets, and phase-by-phase checklist.

---

## Repository Structure

```text
pinhos/
├── main.py                 # Boot entry point, 3-strike crash guard, safe-mode recovery & UI loop
├── version.json            # Semantic version, build target, arch tag, and OTA manifest
├── boards/                 # Hardware Abstraction Layer (HAL)
│   ├── base.py             # Abstract board contract (LCD, input, SD, battery, backlight, audio)
│   ├── picocalc.py         # ClockworkPi PicoCalc driver (SPI LCD, I2C STM32 southbridge, SD, BMP capture)
│   └── generic_spi.py      # Reference profile for custom Pico 2W + SPI LCD + I2C CardKB builds
├── core/                   # Kernel & resource management
│   ├── sandbox.py          # App isolation, sys.modules diffing, descriptor cleanup, GC enforcement
│   ├── swap.py             # Cooperative JSON/binary state offloading to /sd/pinhos/.swap/
│   ├── config.py           # Persistent system, power & network configuration manager (+ snapshots)
│   ├── theme.py            # Unified JSON theme loader, validator & 16-entry RGB565 LUT engine
│   └── logger.py           # Rotating SD logger, breadcrumb crash forensics & tail reader
├── ui/                     # Dual-UI rendering engine (zero full-screen framebuffers)
│   ├── engine.py           # UIEngine: GUI <-> TUI switching, focus routing & dirty-region renders
│   ├── widgets.py          # Shared dirty-tracked widgets (StatusBar, MosaicGrid, TelemetryStrip, etc.)
│   ├── desktop.py          # Android-style Desktop Home workspace (SRAM/CPU sparklines, SWAP/BAT bars, IP, Notes)
│   ├── menu.py             # Android-style hierarchical drill-down menu & 6-category Settings tree
│   ├── _menu_net.py        # On-demand Wi-Fi scan/connect/saved dialogs (keeps menu SRAM low)
│   ├── _log_view.py        # On-demand ListMenu log file picker (system.log, crash.log, web.log)
│   ├── gui.py              # 320x320 graphical card/panel backend
│   └── tui.py              # High-density terminal grid backend
├── net/                    # Connectivity, wireless HID & GitHub distribution
│   ├── wifi.py             # Multi-SSID STA manager, scanner, auto-connect & NTP clock sync
│   ├── sync.py             # GitHub remote version check & theme/app downloader
│   ├── ble.py              # BLE 5.2 HID central host (Phase 6)
│   └── ota.py              # SHA-256 verified atomic OTA updater (Phase 5)
├── web/                    # Embedded browser IDE & telemetry server (Phase 4)
│   ├── __init__.py         # WebPortal factory & lifecycle helpers
│   ├── server.py           # Non-blocking uasyncio HTTP/REST server with CYW43 RX pump & web.log
│   └── static/             # Zero-dependency cyber-amber SPA (App Studio, SD Files, Live Console, Settings)
├── tools/                  # Built-in on-device system & field utilities (APP_META contract)
│   ├── shell.py            # Interactive BusyBox-style CLI shell (pipes, redirects, history, tab-complete)
│   ├── _shell_cmds.py      # On-demand BusyBox system & hardware inspection commands
│   ├── editor.py           # Streaming nano-style text/JSON editor with search, cut/paste & JSON check
│   ├── files.py            # SD & flash file commander with 1 KB text/JSON viewer & hex inspector
│   ├── net_tools.py        # DNS resolver, TCP RTT ping, port scanner, subnet sweep & Wake-on-LAN
│   ├── uart_term.py        # HAL-routed auxiliary UART1 serial console with baud presets & macros
│   └── sysmon.py           # Live SRAM sparkline, GC counter, RP2350 temp/clock, SD benchmark & BL sliders
├── apps/                   # Community & user applets (single-entry APP_META contract)
├── themes/                 # Built-in & user JSON themes (cyber_amber, phosphor_green, arctic_daylight, synthwave_pulse)
├── tests/                  # On-device hardware, SRAM leak, theme, Dual-UI, Phase 3.1 & Phase 4 self-test suite (12/12 PASS)
├── firmware/               # Custom RP2350 PicoCalc MicroPython UF2 builder & frozen Dual-Boot router
│   ├── frozen/_boot.py     # Early hardware init (PicoDisplay, PicoKeyboard, PicoSD, UART0 COM4)
│   ├── frozen/pinhos_boot.py # Cold-boot splash (5s countdown, 0-100% progress bar, version.json), [F1] Recovery, [F2] Boot Menu & [CTRL+C] REPL
│   ├── build_uf2.sh        # Reproducible WSL2/Linux UF2 build script (RPI_PICO2_W)
│   └── dist/               # Compiled pinhos-picocalc-pico2w.uf2 image
├── picocalc.ps1            # Windows PowerShell deployment, sync, and test automation script
├── README.md
└── ROADMAP.md
```

---

## Target Hardware & Development Setup

### Reference Hardware (ClockworkPi PicoCalc)
* **MCU:** Raspberry Pi Pico 2W (RP2350A — Dual ARM Cortex-M33 @ 150 MHz, 520 KB SRAM, 4 MB QSPI Flash, optional RISC-V Hazard3 cores)
* **Wireless:** Infineon CYW43439 (2.4 GHz Wi-Fi 4 `802.11n` + Bluetooth 5.2 / BLE)
* **Display:** 320×320 SPI IPS LCD (RGB565)
* **Input & Power Co-Processor:** Onboard STM32 southbridge over I2C (QWERTY backlit keyboard matrix, battery voltage/charge telemetry, power management)
* **Storage:** Full-size SPI microSD slot (FAT32)

### Quick Start (Windows / PowerShell Workflow)
1. **Flash the PinhOS Base UF2 (One-Time):** Hold **BOOTSEL** on the Pico 2W, connect USB, and drag `firmware/dist/pinhos-picocalc-pico2w.uf2` onto the `RP2350` drive (or rebuild it anytime in WSL2 via `bash firmware/build_uf2.sh`).
2. **Insert a FAT32 microSD card** into the PicoCalc and connect the USB-C port (`COM4` auto-attaches on boot).
3. **Deploy, Probe & Verify:**
   ```powershell
   .\picocalc.ps1 com              # Fast COM4 port & live REPL health check
   .\picocalc.ps1 upload_and_start # Incremental .mpy/SD sync + 5s Boot Guard launch
   .\picocalc.ps1 test             # 12/12 on-device Phase 1–4 self-test gate (auto-restores UI)
   .\picocalc.ps1 stress           # Deep Stress Suite (Gates 13–14 + 7-menu walk, auto-restores UI)
   .\picocalc.ps1 screenshot       # Capture & pull 320x320 4-bit BMP over COM4
   .\scripts\stamp_release.ps1 -Version "1.0.0-alpha.4.2" # Stamp version.json & literals before tagging
   ```
4. **Cold-Boot Hotkeys (during the 5.0s PinhOS splash with live countdown & progress bar):**
   * **Default / `ENTER`:** Boots straight into `/sd/pinhos/main.py` → 5s Boot Guard → PinhOS Dashboard (`ENTER` skips the countdown immediately).
   * **`F1` or `ESC`:** Launches **PinhOS Custom Safe Recovery Mode** (diagnostics, strike reset, config/swap cleanup, `COM4` REPL).
   * **`F2`:** Opens the **PinhOS Dual-Boot Manager** (`PinhOS`, `Safe Recovery`, `Reset Strikes`, `/sd/firmwares/*.uf2` scanner).
   * **`CTRL+C`:** Interrupts boot immediately and drops straight into the MicroPython `>>>` REPL (`COM4` + LCD).
5. **Live Dashboard Hotkeys:**
   * **`TAB` / `CTRL+M`:** Toggle **GUI ↔ TUI** mode live (persisted in `config.json`).
   * **`CTRL+V`:** Toggle launcher layout between **GRID** (3×2 Mosaic) and **LIST** view.
   * **`CTRL+T`:** Cycle all 4 JSON themes live (`cyber_amber` → `phosphor_green` → `arctic_daylight` → `synthwave_pulse`).
   * **`CTRL+P`:** Capture a clean 320×320 4-bit indexed BMP screenshot to `/sd/pinhos/screenshots/` with a confirmation toast (works across dashboard, menus, and all `tools/*.py`).
   * **`CTRL+B` / `CTRL+F` / `CTRL+E` / `CTRL+U` / `CTRL+N` / `CTRL+S`:** Quick-launch BusyBox Shell, File Manager, Text Editor, UART Console, Net Probes, or System Monitor.
   * **`CTRL+L`:** Open the on-device **Log File Picker** (`system.log`, `crash.log`, `web.log`, etc.) with scrollable viewer and clear option.
   * **`CTRL+Z` / `POWER`:** Enter low-power Sleep Mode (5s cancellable countdown, zero backlight, instant key wake; suppressed when `LNK` or `WEB` is active).
   * **`CTRL+Q`:** Toggle non-blocking **COM4 Serial Link (`LNK` badge)**—keeps the UI 100% responsive and suppresses auto-sleep.
   * **`F2`:** Run the 12/12 on-device self-test suite (`tests/selftest.py` + `tests/selftest_p3.py` + `tests/selftest_p4.py`).
   * **`ALT+F5`:** Hard Reload UI & Display Rescue (press twice within 3s for emergency hardware `machine.reset()`).

---

## License

TBD — Core operating system planned under an open-source license, with modular commercial packaging, hardware-locked licensing, and encrypted Pro Field Packs defined for `v1.2.0`.
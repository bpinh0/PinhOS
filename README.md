# 🌲 PinhOS

**A modular, dual-UI MicroPython operating system and portable field cyberdeck platform for the ClockworkPi PicoCalc & Raspberry Pi Pico 2W (RP2350).**

> 🚀 **Status: `v1.0.0-alpha.2` — Phase 1 & Phase 2 Complete & Verified 8/8 on Hardware.** Hardware Abstraction (`boards/`), 3-Strike Boot Guard & BSOD (`main.py`), Sandboxed App Runner (`core/sandbox.py`), Cooperative Swap (`core/swap.py`), Unified Theme Engine (`core/theme.py` + 4 JSON themes), Dual-UI Engine (`ui/` GUI ↔ TUI with 2-row dirty partial redraws & `0 B` SRAM delta), Crash/Breadcrumb Logger & On-Device Log Viewer (`core/logger.py`), 8/8 On-Device Self-Test Gate (`tests/selftest.py`), and Custom RP2350 Auto-Boot UF2 (`firmware/`) are all complete and verified on the ClockworkPi PicoCalc (Pico 2W). **Phase 3 (Built-In BusyBox CLI & Field Utilities) is next.**

---

## Overview

PinhOS turns the ClockworkPi PicoCalc (and custom RP2350 hardware builds) into a fast-booting, deterministic pocket workstation and hardware/network field multitool. Built around a **95% MicroPython / 5% C & Viper** hybrid architecture, it balances instant on-device scripting and over-the-air updates with hardware-accelerated rendering, strict 520 KB SRAM management, and future commercial packaging support.

### Core Capabilities
* **Hardware Abstraction Layer (`boards/`):** Decouples core OS services from hardware pinouts and bus topologies—supporting the ClockworkPi PicoCalc (SPI LCD + I2C STM32 southbridge keyboard/battery + SPI SD) alongside custom Pico 2W + SPI/CardKB cyberdecks, with future portability to ESP32-S3.
* **Resilient Kernel Runtime (`core/`):**
  * **3-Strike Boot Guard & BSOD (`main.py`):** Persistent boot-strike counter with automatic Safe Recovery Mode fallback, unhandled-exception **Blue Screen of Death (`show_bsod()`)** with 1-key recovery, and `[ALT+F5]` Hard Reload (`x2` emergency hardware reset).
  * **Crash Forensics & On-Device Log Viewer (`core/logger.py`):** Rotating `/sd/pinhos/logs/system.log` & `crash.log`, `breadcrumb.json` + `machine.reset_cause()` freeze detection, and a scrollable `[L]` log viewer right on the PicoCalc.
  * **Sandboxed App Execution (`core/sandbox.py`):** Enforces a single `APP_META` / `main(ctx)` contract, snapshots `sys.modules` and `gc.mem_free()` prior to launch, closes leaked file/socket descriptors on exit, purges app modules, and forces garbage collection.
  * **Cooperative Swap Manager (`core/swap.py`):** Serializes inactive task state to `/sd/pinhos/.swap/` to preserve heap headroom inside the RP2350's 520 KB SRAM ceiling.
* **Dual-UI Engine (`ui/`):**
  * **Shared Widget & Focus Model (`ui/widgets.py`):** Dirty-tracked `StatusBar`, `FooterBar`, `Panel`, `ListMenu` (2-row partial redraws), `ProgressBar`, `Dialog`, and `TextView` sized for the PicoCalc's 6×8 display font (`53` chars × 320px) with zero full-screen Python framebuffers.
  * **GUI Mode (`ui/gui.py`) & TUI Mode (`ui/tui.py`):** Live `[TAB]`/`[M]` switching between 320×320 framed graphical cards and high-density terminal layouts with `config.json` persistence and `0 B` SRAM delta—building toward the 3×2 Mosaic & Desktop layouts in `docs/mockups/`.
* **Unified JSON Theme Engine (`core/theme.py` & `themes/`):** Single JSON palette specification (`cyber_amber`, `phosphor_green`, `arctic_daylight`, `synthwave_pulse`) compiled to Core 1-safe in-place 16-entry RGB565 LUTs with live `[T]` hot-swapping and safe built-in fallback.
* **WebPortal Browser IDE (`web/`):** Non-blocking `uasyncio` web server over Wi-Fi providing live SD/flash file management, a browser code editor for `.py` apps and `.json` themes, remote app launching, real-time SRAM/CPU telemetry, and screen capture.
* **GitHub OTA & Community Store (`net/`):** SHA-256-verified over-the-air OS updates and one-click installation of community `.py` / `.mpy` applets and themes directly from GitHub.
* **Wireless & Field Tooling (`tools/` & `net/`):** Built-in BusyBox-style shell, dual-pane file manager, ICMP/TCP/WoL/DNS network probes, hardware UART serial terminal, and BLE 5.2 HID host support for external wireless keyboards, mice, and scanners.

---

## Release Roadmap

| Version | Milestone | Focus & Deliverables |
| :--- | :--- | :--- |
| **`v1.0.0`** | **Foundation & Daily Driver** *(Active)* | `boards/` HAL (PicoCalc & custom SPI/CardKB decks), 3-strike boot guard, sandboxed app runner & `.swap/`, Native LUT + LVGL dual-UI, unified JSON theme engine, WebPortal browser IDE, BusyBox/net/UART field tools, GitHub OTA/App Store, and BLE 5.2 HID host. |
| **`v1.1.0`** | **Power & Native Performance** | Multi-UF2 SD card chainloader (supporting both RP2350 ARM Cortex-M33 and RISC-V Hazard3 `.uf2` images) and dynamic C `.mpy` native modules (`py/dynruntime.h`) for real-time MP3 audio decoding, DSP, and fast framebuffer blits. |
| **`v1.2.0`** | **Commercial Packaging & IP Protection** | Frozen `.mpy` core bytecode compiled into signed RP2350 `.uf2` firmware (flash XIP execution), RP2350 OTP + Secure Boot + `machine.unique_id()` node-locked licensing, and AES-encrypted OTA Pro Field Packs decrypted strictly in SRAM. |

See [`ROADMAP.md`](./ROADMAP.md) for the full technical architecture, contracts, memory budgets, and phase-by-phase checklist.

---

## Repository Structure

```text
pinhos/
├── main.py                 # Boot entry point, 3-strike crash guard, safe-mode recovery shell
├── version.json            # Semantic version, build target, arch tag, and OTA manifest
├── boards/                 # Hardware Abstraction Layer (HAL)
│   ├── base.py             # Abstract board contract (LCD, input, SD, battery, backlight, audio)
│   ├── picocalc.py         # ClockworkPi PicoCalc driver (SPI LCD, I2C STM32 southbridge, SD)
│   └── generic_spi.py      # Reference profile for custom Pico 2W + SPI LCD + I2C CardKB builds
├── core/                   # Kernel & resource management
│   ├── sandbox.py          # App isolation, sys.modules diffing, descriptor cleanup, GC enforcement
│   ├── swap.py             # Cooperative JSON/binary state offloading to /sd/pinhos/.swap/
│   ├── config.py           # Persistent system & network configuration manager
│   ├── theme.py            # Unified JSON theme loader, validator & 16-entry RGB565 LUT engine
│   └── logger.py           # Rotating SD logger, breadcrumb crash forensics & tail reader
├── ui/                     # Dual-UI rendering engine (zero full-screen framebuffers)
│   ├── engine.py           # UIEngine: GUI <-> TUI switching, focus routing & dirty-region renders
│   ├── widgets.py          # Shared dirty-tracked widgets (StatusBar, Panel, ListMenu, TextView, etc.)
│   ├── gui.py              # 320x320 graphical card/panel backend
│   └── tui.py              # High-density terminal grid backend
├── net/                    # Connectivity, wireless HID & GitHub distribution
│   ├── wifi.py             # Multi-SSID STA manager + AP captive fallback mode
│   ├── ble.py              # BLE 5.2 HID central host (keyboards, mice, barcode/RFID scanners)
│   ├── ota.py              # GitHub manifest check, SHA-256 verification, atomic staged updates
│   └── store.py            # GitHub App & Theme Store client (/sd/pinhos/apps/ & /themes/)
├── web/                    # Embedded browser IDE & telemetry server
│   ├── server.py           # Non-blocking uasyncio HTTP/REST server with session PIN/token auth
│   └── static/             # Lightweight SPA frontend (file manager, code editor, live screen)
├── tools/                  # Built-in system & field utilities
│   ├── shell.py            # Interactive BusyBox-style CLI shell
│   ├── files.py            # SD & flash file manager with text/hex viewer
│   ├── net_tools.py        # ICMP ping, TCP port scan, ARP/subnet sweep, Wake-on-LAN, DNS
│   ├── uart_term.py        # Hardware UART serial console with baud presets & macro keys
│   └── sysmon.py           # Real-time SRAM/GC telemetry, RP2350 temp/clock, SD benchmark
├── apps/                   # Community & user applets (single-entry APP_META contract)
├── themes/                 # Built-in & user JSON themes (cyber_amber, phosphor_green, arctic_daylight, synthwave_pulse)
├── tests/                  # On-device hardware, SRAM leak, theme & Dual-UI self-test suite (8/8 PASS)
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
3. **Deploy & Verify:**
   ```powershell
   .\picocalc.ps1 upload_and_start
   .\picocalc.ps1 test
   ```
4. **Cold-Boot Hotkeys (during the 5.0s PinhOS splash with live countdown & progress bar):**
   * **Default / `ENTER`:** Boots straight into `/sd/pinhos/main.py` → 5s Boot Guard → PinhOS Dashboard (`ENTER` skips the countdown immediately).
   * **`F1` or `ESC`:** Launches **PinhOS Custom Safe Recovery Mode** (diagnostics, strike reset, config/swap cleanup, `COM4` REPL).
   * **`F2`:** Opens the **PinhOS Dual-Boot Manager** (`PinhOS`, `Safe Recovery`, `Reset Strikes`, `/sd/firmwares/*.uf2` scanner).
   * **`CTRL+C`:** Interrupts boot immediately and drops straight into the MicroPython `>>>` REPL (`COM4` + LCD).
5. **Live Dashboard Hotkeys:**
   * **`TAB` / `M`:** Toggle **GUI ↔ TUI** mode live (persisted in `config.json`).
   * **`T`:** Cycle all 4 JSON themes live (`cyber_amber` → `phosphor_green` → `arctic_daylight` → `synthwave_pulse`).
   * **`L`:** Open the scrollable on-device **System & Crash Logs** viewer (`S`/`TAB` toggles `system.log`/`crash.log`, `C` clears).
   * **`F2`:** Run the 8/8 on-device self-test suite.
   * **`ALT+F5`:** Hard Reload UI & Display Rescue (press twice within 3s for emergency hardware `machine.reset()`).
   * **`Q`:** Exit cleanly to the `COM4` serial `>>>` REPL.

---

## License

TBD — Core operating system planned under an open-source license, with modular commercial packaging, hardware-locked licensing, and encrypted Pro Field Packs defined for `v1.2.0`.
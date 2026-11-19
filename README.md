# 🌲 PinhOS

**A modular, dual-UI MicroPython operating system and portable field cyberdeck platform for the ClockworkPi PicoCalc & Raspberry Pi Pico 2W (RP2350).**

> 🚀 **Status: `v1.0.0-alpha.1` — Phase 1 Complete & Verified on Hardware.** Hardware Abstraction (`boards/`), 3-Strike Boot Guard (`main.py`), Sandboxed App Runner (`core/sandbox.py`), Cooperative Swap (`core/swap.py`), 5/5 On-Device Self-Test Gate (`tests/selftest.py`), and Custom RP2350 Auto-Boot UF2 (`firmware/`) are all complete and verified on the ClockworkPi PicoCalc (Pico 2W). **Phase 2 (Dual-UI Engine & Unified Theme System) is next.**

---

## Overview

PinhOS turns the ClockworkPi PicoCalc (and custom RP2350 hardware builds) into a fast-booting, deterministic pocket workstation and hardware/network field multitool. Built around a **95% MicroPython / 5% C & Viper** hybrid architecture, it balances instant on-device scripting and over-the-air updates with hardware-accelerated rendering, strict 520 KB SRAM management, and future commercial packaging support.

### Core Capabilities
* **Hardware Abstraction Layer (`boards/`):** Decouples core OS services from hardware pinouts and bus topologies—supporting the ClockworkPi PicoCalc (SPI LCD + I2C STM32 southbridge keyboard/battery + SPI SD) alongside custom Pico 2W + SPI/CardKB cyberdecks, with future portability to ESP32-S3.
* **Resilient Kernel Runtime (`core/`):**
  * **3-Strike Boot Guard (`main.py`):** Persistent boot-strike counter with automatic fallback to a minimal serial/Wi-Fi recovery shell if a startup script, theme, or config faults.
  * **Sandboxed App Execution (`core/sandbox.py`):** Enforces a single `APP_META` / `main(ctx)` contract, snapshots `sys.modules` and `gc.mem_free()` prior to launch, closes leaked file/socket descriptors on exit, purges app modules, and forces garbage collection.
  * **Cooperative Swap Manager (`core/swap.py`):** Serializes inactive task state to `/sd/pinhos/.swap/` to preserve heap headroom inside the RP2350's 520 KB SRAM ceiling.
* **Dual-UI Engine (`ui/`):**
  * **Native Mode:** Ultra-fast 4-bit indexed framebuffer with `@micropython.viper` RGB565 LUT palette expansion, signature pixel-art pine tree branding, and instant keyboard navigation.
  * **LVGL Desktop Mode:** Full C-accelerated windowed desktop interface with app drawer, floating telemetry/notes cards, and taskbar.
* **Unified JSON Theme Engine (`themes/`):** Single JSON palette & typography specification (`amber_phosphor`, `cyber_cyan`, `matrix_green`, `high_contrast`) dynamically applied across Native Mode, LVGL Desktop Mode, and the browser WebPortal.
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
│   └── logger.py           # Ring-buffer & SD diagnostic logger
├── ui/                     # Dual rendering engines & shared theming
│   ├── theme.py            # Unified JSON theme loader & RGB565 LUT generator
│   ├── native/             # 4-bit indexed framebuffer, Viper blitter, pixel pine tree splash & widgets
│   └── lvgl/               # LVGL windowed desktop shell, app dock, telemetry widgets & taskbar
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
├── themes/                 # Built-in & user JSON themes (amber_phosphor.json default)
├── tests/                  # On-device hardware, SRAM leak, and boot-guard self-test suite (5/5 PASS)
├── firmware/               # Custom RP2350 PicoCalc MicroPython UF2 builder & frozen Dual-Boot router
│   ├── frozen/_boot.py     # Early hardware init (PicoDisplay, PicoKeyboard, PicoSD, UART0 COM4)
│   ├── frozen/pinhos_boot.py # Cold-boot splash, [ESC/F1] REPL escape & [F2] Dual-Boot Manager
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
4. **Cold-Boot Hotkeys (during the 600ms PinhOS splash):**
   * **Default:** Boots straight into `/sd/pinhos/main.py` → 5s Boot Guard → PinhOS Dashboard.
   * **Hold `ESC` or `F1`:** Drops cleanly into the MicroPython `>>>` REPL (`COM4` + LCD).
   * **Hold `F2`:** Opens the **PinhOS Dual-Boot Manager** (`PinhOS`, `REPL`, `Reset Strikes`, `/sd/firmwares/*.uf2`).

---

## License

TBD — Core operating system planned under an open-source license, with modular commercial packaging, hardware-locked licensing, and encrypted Pro Field Packs defined for `v1.2.0`.
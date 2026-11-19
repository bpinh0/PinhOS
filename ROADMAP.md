# 🌲 PinhOS — Architectural Specification & Engineering Roadmap

> **Target Platform:** ClockworkPi PicoCalc (Raspberry Pi Pico 2W / RP2350 — Dual ARM Cortex-M33 @ 150 MHz, 520 KB SRAM, 4 MB Flash, CYW43439 Wi-Fi 4 + BLE 5.2, 320×320 SPI LCD, I2C STM32 Southbridge, SPI microSD).  
> **Current Status:** Active Development — `v1.0.0-alpha.2` (**Phase 1 + Phase 2 Complete & Verified 8/8 on Hardware** — Dual-UI Engine, Unified Theme System, Crash/Breadcrumb Logger & BSOD; **Phase 3 next**).

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
Every applet in `/sd/pinhos/apps/<app_name>/` exposes a single `main(ctx)` entry point and module-level metadata dictionary so the launcher, Store, and sandbox can validate memory requirements before execution:
```python
APP_META = {
    "id": "uart_term",
    "name": "UART Console",
    "version": "1.0.0",
    "category": "Field Tools",       # Field Tools | Network | System | Media | Games
    "description": "Hardware serial terminal with baud presets and macros",
    "entry": "main",
    "min_sram": 32768,               # Minimum free bytes required before launch
    "ui_modes": ["native", "lvgl"],  # Supported rendering backends
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
  - Initialize `/sd/pinhos/` directory hierarchy (`boards/`, `core/`, `ui/`, `net/`, `web/`, `tools/`, `apps/`, `themes/`, `.swap/`, `logs/`).
  - Create `version.json` containing semantic version, build timestamp, target architecture (`armv7emsp`), and OTA channel metadata.
- [x] **1.2 Board Hardware Abstraction Layer (`boards/`):**
  - `boards/base.py`: Define abstract base class and capability flags for display (`320x320` RGB565 blit/fill), keyboard/pointer input queue, microSD mount/unmount, battery voltage/percentage/charging state, PWM backlight (`0–100%`), PWM/I2S audio, and RTC.
  - `boards/picocalc.py`: Full hardware driver for ClockworkPi PicoCalc (SPI LCD controller, I2C STM32 southbridge keyboard scan + modifier decoding + battery registers, SPI SD card mount with retry logic, keyboard & screen backlight PWM).
  - `boards/generic_spi.py`: Configurable fallback driver for bare Pico 2W setups using standard ST7789/ILI9341 SPI displays and I2C CardKB keyboards.
  - Board auto-detection / `config.json` profile selector at boot.
- [x] **1.3 Crash-Proof 3-Strike Boot Guard (`main.py`):**
  - Read and increment `boot_strikes` in persistent flash state prior to mounting SD or importing UI/network modules.
  - Reset `boot_strikes = 0` only after the main event loop runs cleanly for `5 seconds` (or upon explicit self-test pass).
  - Trigger **Safe Recovery Mode** when `boot_strikes >= 3`: boots with minimal framebuffer text output, USB serial REPL access, and a stripped-down emergency WebPortal to restore configs or roll back OTA updates.
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
  - Precompute 16-entry RGB565 LUT arrays applied in-place to `boards/picocalc.py` (Core 1-safe, zero full-screen framebuffer allocation) with runtime `[T]` hot-swapping and `config.json` persistence.
- [x] **2.2 Shared Widget Toolkit & Dual Rendering Backends (`ui/widgets.py`, `ui/gui.py`, `ui/tui.py`):**
  - Reusable dirty-tracked widgets (`StatusBar`, `FooterBar`, `Panel`, `ListMenu`, `ProgressBar`, `Dialog`, `TextView`) with 2-row partial redraws on `ListMenu` navigation (`delta=0B` SRAM verified on hardware).
  - **GUI Mode (320×320 Graphical):** Framed panels, accent header/footer bars, bordered cards, and graphical progress indicators.
  - **TUI Mode (High-Density Terminal):** Crisp monochrome/accent grid layout, dense list rows, ASCII dividers, and minimal draw overhead.
- [x] **2.3 Seamless Live UI Mode Switcher (`ui/engine.py`):**
  - Switch live between GUI and TUI modes (`[TAB]` / `[M]`) and cycle themes (`[T]`) with deterministic backend cleanup, `config.json` persistence, and `< 2 KB` SRAM delta (`0 B` verified on hardware).
- [x] **2.4 Crash Forensics, BSOD Guard & On-Device Log Viewer (`core/logger.py` & `main.py`):**
  - Persistent `system.log` / `crash.log` with rotation, `breadcrumb.json` + `machine.reset_cause()` unclean-shutdown detection, `[L]` scrollable Dual-UI log viewer, `[ALT+F5]` Hard Reload (`x2` emergency reset), and `show_bsod()` fault fallback (**8/8 PASS verified on PicoCalc hardware**).

---

### Phase 3: Built-In BusyBox CLI & Field Utilities (`tools/`)
- [ ] **3.1 Interactive Shell (`tools/shell.py`):**
  - Command-line REPL with command history, path tab-completion, environment variables, 53-column 6×8 scrolling output (`TextView`), and core UNIX-style commands (`ls`, `cd`, `cat`, `cp`, `mv`, `rm`, `mkdir`, `df`, `free`, `ps`, `uname`, `logs`, `reboot`).
  - Add `[ALT+Q]` or confirmation guard for serial `COM4` REPL exit so standalone users cannot accidentally strand the UI.
- [ ] **3.2 File Manager (`tools/files.py`):**
  - Keyboard-driven file browser across `/sd/` and internal flash with file size/timestamp metadata, copy/move/rename/delete operations, streaming text/JSON viewer (1 KB chunked reads to protect RP2350 SRAM), and hex dump inspector.
- [ ] **3.3 Network & Hardware Field Utilities (`tools/net_tools.py` & `tools/uart_term.py`):**
  - **Net Probes:** Raw ICMP `ping` with RTT stats, fast async TCP port scanner, local subnet host sweep, Wake-on-LAN (`WoL`) magic packet sender, and DNS resolver.
  - **UART Serial Console:** Hardware UART terminal (`boards/` UART pins) with configurable baud rates (`9600` to `921600`), `8N1` framing options, ASCII/Hex display toggle, SD session logging, and programmable F-key macro strings.
- [ ] **3.4 System Monitor, Settings & Launcher Polish (`tools/sysmon.py`):**
  - Live SRAM free/allocated sparkline, GC cycle counter, RP2350 internal temperature & CPU frequency readout, SD read/write speed benchmark, backlight brightness slider, and UI/theme switcher.
  - Evolve the GUI launcher toward the `docs/mockups/` 3×2 icon-tile **Mosaic** & **Desktop** layouts (primitive-drawn icons + `SYS TELEMETRY` / `QUICK NOTES` cards) as Phase 3 tools populate the 6 top-level categories (`Dashboard`, `Apps & Studio`, `Terminal & Toolkit`, `Files /sd`, `HW Lab`, `Sys & OTA`).

---

### Phase 4: WebPortal Browser IDE (`web/`)
- [ ] **4.1 Embedded Async Web Server (`web/server.py`):**
  - Non-blocking `uasyncio` HTTP server running alongside the UI loop with configurable port and 6-digit PIN / session token authentication.
- [ ] **4.2 Browser IDE & Telemetry Workspace (`web/static/`):**
  - Zero-dependency lightweight web frontend served directly from the PicoCalc.
  - **File Explorer:** Browse, upload, download, rename, and delete files on `/sd/` and flash.
  - **Live Code & Theme Editor:** Edit `.py` apps or `.json` themes in the browser, save directly to SD, and trigger remote execution inside `core/sandbox.py` with live stdout/traceback streaming.
  - **Device Dashboard:** Live SRAM/battery/Wi-Fi telemetry and on-demand framebuffer screenshot capture (`PNG`/`BMP`).

---

### Phase 5: Wi-Fi Manager, GitHub OTA & App/Theme Store (`net/`)
- [ ] **5.1 Wi-Fi Manager (`net/wifi.py`):**
  - Multi-network credential store (`wifi.json`), signal strength scanner, non-blocking auto-reconnect, and automatic SoftAP hotspot fallback (`PinhOS-Setup`) for headless field configuration via WebPortal.
- [ ] **5.2 GitHub OTA Updater (`net/ota.py`):**
  - Fetch remote `version.json` and file manifest from configured GitHub release/branch.
  - Download changed files into `/sd/pinhos/.ota_staging/`, verify SHA-256 digests, atomically swap into place, and leverage Phase 1's 3-strike Boot Guard for automatic recovery if an update fails to boot.
- [ ] **5.3 GitHub App & Theme Store (`net/store.py`):**
  - Fetch curated catalog index (`store_index.json`) of community applets and JSON themes.
  - Display category filters, version tags, `min_sram` compatibility badges, and one-click install/update/remove into `/sd/pinhos/apps/` and `/sd/pinhos/themes/`.

---

### Phase 6: Bluetooth 5.2 HID Host & Peripherals (`net/ble.py`)
- [ ] **6.1 BLE Central & Device Pairing:**
  - Utilize CYW43439 `ubluetooth` (NimBLE) to scan, pair, bond, and auto-reconnect with standard BLE HID peripherals (full-size keyboards, mini trackballs/mice, wireless barcode/RFID scanners).
- [ ] **6.2 Unified Input Multiplexer:**
  - Merge incoming BLE HID keycodes and relative pointer events into the `boards/` input queue so external wireless peripherals work transparently across Native Mode, LVGL Desktop Mode, and all sandboxed apps.

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
<div align="center">

# ⚡ PinhOS
### **A Modular MicroPython Cyberdeck OS & Field Toolkit for the ClockworkPi PicoCalc**

[![Target Hardware](https://img.shields.io/badge/Hardware-ClockworkPi_PicoCalc-00ff9c?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://www.clockworkpi.com/)
[![MCU](https://img.shields.io/badge/MCU-RP2350_%7C_Pico_2W-ff6b00?style=for-the-badge)](https://www.raspberrypi.com/products/raspberry-pi-pico-2/)
[![Runtime](https://img.shields.io/badge/Runtime-MicroPython-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://micropython.org/)
[![Release Target](https://img.shields.io/badge/Target-v1.0.0--dev-blueviolet?style=for-the-badge)](#%EF%B8%8F-roadmap--release-channels)
[![License](https://img.shields.io/badge/License-MIT-lightgrey?style=for-the-badge)](#license)

*Turn your PicoCalc into a pocket-sized network & hardware cyberdeck—complete with a live browser WebPortal, isolated App Sandbox, BusyBox diagnostics, SD state-swapping, and dual Native/LVGL graphics.*

</div>

---

## 🚀 Why PinhOS?

Most microcontroller firmwares force a trade-off between raw scripting freedom and system stability. **PinhOS** is engineered from the ground up for the **RP2350 (520 KB SRAM)** to deliver real OS resilience without sacrificing hackability:

- 🛡️ **Crash-Proof Architecture:** Breadcrumb boot tracking, BSOD stack-trace forensics (`crash.log`), 3-strike automatic Safe Mode, and offline `.versions/` rollbacks ensure a bad script or theme never bricks your deck.
- 🧠 **Cooperative SD Memory Swap (`core/swap.py`):** Automatically spills cold buffers (logs, terminal scrollback, catalog caches) to `/sd/pinhos/.swap/` before launching heavy apps or LVGL—freeing contiguous SRAM on demand while protecting SD flash wear.
- 🌐 **Live Theme-Synced WebPortal:** Control your PicoCalc from any desktop browser over Wi-Fi or USB (`COM4`) with a real-time HTML5 `<canvas>` screen mirror, virtual D-Pad/F-Keys, SD file manager, and an online **App Studio** code editor.
- 📦 **Zero-Pollution App Sandbox:** Every app executes in a clean namespace with `sys.modules` snapshotting and automatic garbage collection on exit.
- 🎨 **Dual-Backend Graphics Engine:** Runs blazing-fast on the native **16-color RGB565 LUT** engine by default, with an optional **LVGL** backend toggle that automatically falls back to Native LUT if firmware support or RAM is unavailable.

---

## ✨ Core Features & Cyberdeck Suite

### 1. Six-Domain Main Deck
1. **📊 Dashboard & Telemetry (`F1`):** Real-time CPU load, `gc` SRAM free/used, SD Swap usage, Wi-Fi LAN IP/RSSI, and STM32 PMU battery cell voltage & runtime estimates.
2. **🧩 Apps & Developer Studio:**
   - **App Launcher & Git Store:** Standard `APP_META` manifests with `F5` metadata inspection.
   - **On-Device & Browser Dev Studio:** Edit Python apps in your browser, upload via drag-and-drop, or hot-push over USB (`dev_watch.ps1`) and run immediately inside the isolated sandbox with live console streaming.
   - **Scratchpad Notes:** Lightweight Markdown/text notes synced between the PicoCalc and WebPortal.
3. **💻 Terminal & Cyberdeck Field Toolkit:**
   - **BusyBox-Style Shell:** Built-in `ping` (TCP RTT), `scan` (non-blocking TCP port scanner), `wol` (Wake-on-LAN magic packets), `nslookup`, `ifconfig`, `dmesg`, and `py` one-liner evaluator.
   - **Serial UART Console (`minicom` mode):** Connect directly to routers, switches, ESP32s, or headless servers via exposed `UART0`/`UART1` pins (`9600`–`921600` baud) with SD session logging.
   - **USB / SD Transfer Bridge:** Expose `/sd` over USB Mass Storage (firmware-dependent) or manage files wirelessly via the WebPortal REST API.
4. **📁 File Commander (`/sd`):** Full directory browser, custom extension-to-app associations (`Open With...`), `F5` file details, framebuffer `.bmp` screenshots (`F10`/`Ctrl+P`), and storage analyzer.
5. **🔧 Hardware & Diagnostics Lab:** Live GPIO/Pinout inspector (`IN`/`OUT`/`ADC`), I2C bus scanner, **PWM / Square-Wave Signal Generator** (`1 Hz`–`100 kHz`), crash forensics, and background RTC Pomodoro/Alarm timer.
6. **⚙️ System, Network & Git OTA:** Configurable `F1`–`F10` multi-page hotkeys, custom JSON themes (`LIST` & `MOSAIC` grids), optional Desktop Mode, screensaver, SemVer release channel selector (`STABLE` / `BETA` / `DEV`), and 1-click version rollback.

---

## 🏗️ System Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│  IMMUTABLE BOOTLOADER (.uf2 on RP2350 Flash)                       │
│  └─ Mounts /sd ──▶ Checks 3-Strike Breadcrumb ──▶ Boots /sd/pinhos │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────┐
│  LIVE OS PAYLOAD (/sd/pinhos/ — Updated via Git OTA or COM4)       │
│                                                                    │
│  ├── main.py              # Safe-mode boot guard & reload loop     │
│  ├── version.json         # SemVer 2.0.0 metadata & changelog      │
│  ├── core/                                                         │
│  │   ├── kernel.py        # State machine, atomic I/O, BSOD        │
│  │   ├── swap.py          # Cooperative SD state spill & SwapPager │
│  │   ├── sandbox.py       # Isolated app namespace & RAM cleanup   │
│  │   └── bridge.py        # <<PINHOS:...>> framed UART protocol    │
│  ├── ui/                                                           │
│  │   ├── renderer.py      # Native 16-color LUT & dirty-rect draw  │
│  │   ├── lvgl_backend.py  # Optional LVGL adapter + auto-fallback  │
│  │   ├── themes.py        # Unified LUT + LVGL JSON theme engine   │
│  │   └── desktop.py       # Optional icon & taskbar workspace      │
│  ├── net/                 # Wi-Fi retry, NTP, TCP ping, GitHub OTA │
│  ├── web/                 # Non-blocking HTTP server & WebPortal   │
│  └── apps/                # Shell, Files, Store, Dev Studio, Lab   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Hardware Requirements & Quick Start

### Hardware
- **Device:** ClockworkPi PicoCalc
- **Compute Module:** Raspberry Pi Pico 2W (RP2350, Wi-Fi CYW43439)
- **Storage:** FAT32 microSD card mounted at `/sd`

### Deploying via USB (`picocalc.ps1`)
Connect your PicoCalc to Windows over USB (`COM4`) and push the OS directly to `/sd/pinhos/`:

```powershell
# Full sync and reboot into PinhOS
.\picocalc.ps1 upload_and_start

# Hot-push a single app file into the isolated sandbox
.\picocalc.ps1 hot_write .\apps\my_app.py /sd/pinhos/apps/my_app.py
```

### Accessing the WebPortal
1. Connect to Wi-Fi under **System, Network & OTA -> Network**.
2. Press **`F2`** (or open the Dashboard with **`F1`**) to view your assigned LAN URL (`http://<pico-ip>:8080`).
3. Open the URL in any browser for live screen mirroring, remote D-Pad/F-Key input, SD file transfers, and the browser-based **App Studio**.

---

## 🗺️ Roadmap & Release Channels

PinhOS follows strict **SemVer 2.0.0** pre-release channels targeting **`v1.0.0`**:
- `1.0.0-dev.<build>+<sha>` — Active development iterations
- `1.0.0-beta.<n>+<sha>` — Feature-complete public testing
- `1.0.0-rc.<n>+<sha>` — Release candidate freeze
- `1.0.0` — Official stable release

| Phase | Milestone | Status |
| :--- | :--- | :---: |
| **Phase 1** | Modular `/sd/pinhos/` architecture, 6-domain menu, `version.json` & core bug fixes | 🚧 In Progress |
| **Phase 2** | GitHub OTA updater, local `.versions/` instant rollback & bootloader `.uf2` scripts | 📋 Planned |
| **Phase 3** | Theme-synced WebPortal, App Developer Studio & `F5` file associations | 📋 Planned |
| **Phase 4** | Dual-backend UI (`NATIVE LUT` + optional `LVGL` with auto-fallback) & Desktop Mode | 📋 Planned |
| **Phase 5** | Cyberdeck Field Toolkit (UART `minicom`, Port Scanner, WoL, PWM gen, USB/SD bridge) | 📋 Planned |

Full engineering specifications live in [`ROADMAP.md`](ROADMAP.md).

---

## 🤝 Contributing & Building Apps

Want to write an app for PinhOS? Drop a `.py` file into `/sd/pinhos/apps/` with a standard `APP_META` header:

```python
APP_META = {
    "name": "Hello Cyberdeck",
    "version": "1.0.0",
    "author": "YourName",
    "desc": "Minimal sandboxed PinhOS app",
    "ext": []
}

import picocalc, time

d = picocalc.display
d.fill(0)
d.text("HELLO PINHOS!", 95, 150, 10)
d.show()

while True:
    if picocalc.keyboard.read() == "\x1b":  # ESC exits cleanly back to PinhOS
        break
    time.sleep_ms(20)
```

---

## 📄 License

Released under the [MIT License](LICENSE). Built for the ClockworkPi & RP2350 maker community.
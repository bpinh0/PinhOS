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

## 🖼️ UI & WebPortal Previews

| Native 16-Color LUT (`Cyber Amber`) | LVGL Mosaic Grid (`Synthwave Pulse`) |
| :---: | :---: |
| <img src="docs/mockups/ui_native_cyber_amber.jpg" alt="Native LUT Cyber Amber" width="320"/> | <img src="docs/mockups/ui_lvgl_synthwave_pulse.jpg" alt="LVGL Mosaic Synthwave Pulse" width="320"/> |

| Native LUT (`Phosphor Green`) | Native LUT (`Arctic Daylight`) |
| :---: | :---: |
| <img src="docs/mockups/ui_native_phosphor_green.jpg" alt="Native LUT Phosphor Green" width="320"/> | <img src="docs/mockups/ui_native_arctic_daylight.jpg" alt="Native LUT Arctic Daylight" width="320"/> |

<div align="center">
  <img src="docs/mockups/webportal_studio.jpg" alt="PinhOS Theme-Synced WebPortal & App Studio" width="680"/>
  <br/>
  <sub><b>Theme-Synced Browser WebPortal:</b> Real-time 320×320 screen mirror, virtual D-Pad/F-Keys, SD file manager, and live App Studio sandbox.</sub>
</div>

---

## 🚀 Why PinhOS?

Most microcontroller firmwares force a trade-off between raw scripting freedom and system stability. **PinhOS** is engineered from the ground up for the **RP2350 (520 KB SRAM)** to deliver real OS resilience without sacrificing hackability:

- 🛡️ **Crash-Proof Architecture:** Breadcrumb boot tracking, BSOD stack-trace forensics (`crash.log`), 3-strike automatic Safe Mode, and offline `.versions/` rollbacks ensure a bad script or theme never bricks your deck.
- 🧠 **Cooperative SD Memory Swap (`core/swap.py`):** Automatically spills cold buffers (logs, terminal scrollback, catalog caches) to `/sd/pinhos/.swap/` before launching heavy apps or LVGL—freeing contiguous SRAM on demand while protecting SD flash wear.
- 🌐 **Live Theme-Synced WebPortal:** Control your PicoCalc from any desktop browser over Wi-Fi or USB (`COM4`) with a real-time HTML5 `<canvas>` screen mirror, virtual D-Pad/F-Keys, SD file manager, and an online **App Studio** code editor.
- 📦 **Zero-Pollution App Sandbox:** Every app executes in a clean namespace with `sys.modules` snapshotting and automatic garbage collection on exit.
- 🎨 **Dual-Backend Graphics Engine & Unified JSON Themes:** Runs blazing-fast on the native **16-color RGB565 LUT** engine by default, with an optional **LVGL** backend toggle that automatically falls back to Native LUT if firmware support or RAM is unavailable.

---

## ✨ Core Features & Cyberdeck Suite

### Six-Domain Main Deck
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
│  ├── themes/              # Starter JSON themes (Amber, Green...)  │
│  ├── net/                 # Wi-Fi retry, NTP, TCP ping, GitHub OTA │
│  ├── web/                 # Non-blocking HTTP server & WebPortal   │
│  └── apps/                # Shell, Files, Store, Dev Studio, Lab   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🎨 Custom Theme Engine & Theme Building Guide

PinhOS uses a **single-source JSON theme architecture** (`/sd/pinhos/themes/<theme_id>.json`) that drives the entire visual stack across both hardware renderers and the browser WebPortal—with zero duplicated color definitions or firmware rebuilds.

### How a Theme Compiles Across Backends
When `ui/themes.py` loads a `.json` preset, it compiles the 12 semantic color tokens into three targets simultaneously:
1. **Native 16-Color RGB565 LUT (`ui/renderer.py`):** Converts `#RRGGBB` hex strings into big-endian `RGB565` palette indices (`0–11`), reserving slots `12–15` for system/BSOD states so dirty-rectangle redraws stay fast and flicker-free.
2. **LVGL Style Objects (`ui/lvgl_backend.py`):** Maps `colors.*` and `lvgl.*` properties (`card_radius`, `border_width`, `glow_alpha`) into reusable `lv.style_t` containers for cards, headers, and focus states.
3. **Browser WebPortal (`web/server.py`):** Injects `colors.bg`, `colors.surface`, `colors.fg`, `colors.fg_muted`, `colors.accent`, and `colors.border` directly into `:root` CSS custom properties (`--bg`, `--surface`, `--fg`, `--accent`, etc.) on page load.

### Schema Reference (`themes/<theme_id>.json`)

| Key | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `id` | `string` | Yes | Unique snake_case identifier matching the filename (e.g., `cyber_amber`). |
| `name` | `string` | Yes | Human-readable display name shown in **Display & Themes** settings. |
| `author` | `string` | No | Theme creator handle. |
| `version` | `string` | No | SemVer version of the theme preset (e.g., `1.0.0`). |
| `layout` | `"LIST"` or `"MOSAIC"` | Yes | Default Main Deck layout (`LIST` for 6-row menu, `MOSAIC` for 2×3 icon cards). |
| `font_scale` | `float` | No | UI font multiplier (`1.0`, `1.25`, or `1.5`). Defaults to `1.0`. |
| `lvgl.card_radius` | `int` | No | Corner radius in pixels for LVGL containers (`0`–`16`). |
| `lvgl.border_width` | `int` | No | Outline thickness in pixels for LVGL cards (`1`–`3`). |
| `lvgl.glow_alpha` | `int` | No | Focus shadow/glow opacity (`0`–`255`, `0` disables glow). |
| `colors.bg` | `#RRGGBB` | Yes | Primary screen background. |
| `colors.surface` | `#RRGGBB` | Yes | Card, modal, and telemetry box background. |
| `colors.fg` | `#RRGGBB` | Yes | Primary text and icon stroke color. |
| `colors.fg_muted` | `#RRGGBB` | Yes | Secondary labels, inactive tabs, and subtle dividers. |
| `colors.accent` | `#RRGGBB` | Yes | Secondary highlight color (badges, active links, progress bars). |
| `colors.accent_fg` | `#RRGGBB` | Yes | High-contrast text color rendered on top of `accent`. |
| `colors.border` | `#RRGGBB` | Yes | 1px Native frames and LVGL card borders. |
| `colors.sel_bg` | `#RRGGBB` | Yes | Active menu cursor / selected card fill. |
| `colors.sel_fg` | `#RRGGBB` | Yes | Active menu cursor / selected card text. |
| `colors.ok` / `warn` / `err` | `#RRGGBB` | Yes | Semantic status indicators (Wi-Fi/Battery OK, low-RAM warning, fatal error). |

### Example Theme (`themes/cyber_amber.json`)

```json
{
  "id": "cyber_amber",
  "name": "Cyber Amber",
  "author": "bpinh0",
  "version": "1.0.0",
  "layout": "LIST",
  "font_scale": 1.0,
  "lvgl": { "card_radius": 8, "border_width": 2, "glow_alpha": 40 },
  "colors": {
    "bg": "#0A0C10", "surface": "#12161F", "fg": "#FFB000", "fg_muted": "#9E7216",
    "accent": "#00E5FF", "accent_fg": "#0A0C10", "border": "#FFB000",
    "sel_bg": "#FFB000", "sel_fg": "#0A0C10", "ok": "#00FF9C", "warn": "#FF9900", "err": "#FF3355"
  }
}
```

### Creating & Installing Your Own Theme
1. **Copy an existing preset** from `themes/` (e.g., `themes/cyber_amber.json`) and save it as `themes/<your_theme>.json` using valid JSON and 6-digit `#RRGGBB` hex colors.
2. **Test on your PicoCalc** via USB (`.\picocalc.ps1 hot_write .\themes\my_theme.json /sd/pinhos/themes/my_theme.json`), WebPortal **SD Files** upload, or **Sync `/themes` from Git**.
3. **Activate it** under **System, Network & OTA -> Display & Themes -> Theme Selector**.

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
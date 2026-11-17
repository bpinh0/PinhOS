# PinhOS v2.0.0 — Master Engineering Spec (RP2350 / Pico 2W)

You are updating **PinhOS** (`pinhos_os.py` + `picocalc.ps1`), a MicroPython cyberdeck OS running on a ClockworkPi PicoCalc powered by a **Raspberry Pi Pico 2W (RP2350, 520 KB SRAM, CYW43439 Wi-Fi, 320x320 16-color LUT display)**.

### Hardware, Stability & Architecture Rules (CRITICAL)
1. **Immutable Bootloader UF2 + SD-Card OS Architecture:**
   - Do **not** attempt to compile or rebuild `.uf2` binaries on the Pico 2W.
   - Separate the **Frozen UF2 Bootstrapper** (built once via PC/WSL2/GitHub Actions: mounts `/sd`, verifies `/sd/pinhos/main.py`, and launches PinhOS—falling back to a minimal recovery shell if `/sd` fails) from the **Live OS on `/sd/pinhos/`** (updated in seconds via GitHub OTA / HTTP file sync + soft-reboot).
2. **Dual-Backend Graphics Engine (Native LUT + Optional LVGL with Crash Fallback):**
   - Retain the fast, zero-dependency **`picocalc.display` 16-color LUT renderer** as the default/primary engine, Safe-Mode renderer, and BSOD renderer.
   - Support an optional **`"ui_backend": "NATIVE" | "LVGL"`** toggle in Display Settings (`"NATIVE"` by default).
   - When `"LVGL"` is enabled, attempt to initialize `lvgl` via a clean adapter (`ui/lvgl_backend.py`). If `import lvgl` fails (missing C module in firmware), `MemoryError` occurs, or any unhandled LVGL rendering exception happens at runtime, **automatically catch the fault, revert `ui_backend` to `"NATIVE"` in `config.json`, log the fallback event, and seamlessly continue rendering with `picocalc.display`**—never crashing the OS.
3. **SD-Backed Cooperative Memory Swap & Spill (`core/swap.py`):**
   - Because RP2350 MicroPython lacks hardware MMU virtual memory, implement explicit **cooperative context spilling** backed by `/sd/pinhos/.swap/` (wiped cleanly on every boot).
   - Whenever `gc.mem_free()` drops below a configurable threshold (default `65 KB`) or right before launching a sandboxed app / LVGL view, serialize cold in-memory buffers (`sys_logs` history, terminal scrollback, cached GitHub Store/Releases JSON lists, and inactive UI caches) to `/sd/pinhos/.swap/spill.json`, clear them from RAM, and call `gc.collect()`. Reload them automatically upon exit.
   - Provide a reusable `SwapPager` helper for large log files (`system.log`, `crash.log`), GitHub commit lists, and large text/hex files in the File Manager so only the visible window (`~15 lines`) stays in SRAM while scrolling from `/sd`.
   - **Wear-Leveling Guard:** Strictly forbid swap writes inside the 1-second tick loop—only spill on view/app transitions or low-RAM triggers. Expose Swap telemetry (`Swap Used KB`) in Dashboard (`F1`) and Hardware Debug, plus Enable/Disable and threshold settings.
4. **SRAM & Atomic Storage Guardrails:**
   - Use **lazy imports** (`__import__`) for heavy views (App Store, Dev Studio, Field Toolkit, Synth, GPIO/Pinout, Desktop Mode, WebPortal) so only active modules occupy heap RAM. Call `gc.collect()` on every view transition.
   - Wrap all SD-card writes (OTA updates, config saves, logs) in atomic **write-to-`.tmp` -> verify -> `os.rename()`** operations so a power cut or Wi-Fi drop never corrupts `/sd/pinhos/`.
5. **Core 1 LCD DMA Safety:**
   - Never poll `wlan.status()` or block on network sockets while Core 1 LCD refresh is active without non-blocking sockets or `d.stopRefresh()` / `d.recoverRefresh()` guards (see existing `connect_wifi` pattern).
6. **App Sandboxing (Zero OS Pollution):**
   - Execute all user/test apps inside an isolated namespace dictionary (`{"__name__": "__main__", "picocalc": picocalc}`), snapshot `sys.modules.keys()` before launch, and purge newly imported app modules + run `gc.collect()` on exit.
7. **Deployment Compatibility:**
   - Keep `picocalc.ps1` working seamlessly—update `upload_and_start` to sync the refactored directory structure to `/sd/pinhos/` and match the active theme colors on the upload progress bar.

---

## Phase 1: Critical Bug Fixes (Implement & Verify First)
1. **Header Clock & Flicker-Free Telemetry Refresh:**
   - Fix `run()` so the header clock updates every 1 second even when idle on menus (`active_view is None`), not just on navigation.
   - Remove the redundant `TIME:` line from the menu info box in `draw_menu()` (keep the clock exclusively in the subheader).
   - Add a `draw_status_tick()` method that performs **dirty-rectangle partial redraws** of only the header clock (`x=266, y=28`), battery/Wi-Fi badges, and dashboard gauges—eliminating full-screen flicker.
2. **`LNK` Badge State & `F4` Toggle:**
   - Track actual serial/bridge link state (`bridge_enabled` + active `COM4` heartbeat timeout) instead of permanently showing `LNK` whenever `bridge_policy == "TRUST"`.
   - Map **`F4`** (`\x84` / `\x1bOS` / `\x1b[14~`) in `read_key()` and `handle_virtual_key()` to toggle the `LNK` bridge connection on/off (mirroring `F2` for WebPortal and `F3` for Mouse).
3. **NTP Sync Error Handling -> BSOD:**
   - In `sync_ntp_clock()`, route fatal NTP/socket errors to `self.log_exception("NTP_SYNC", e, show_bsod=True)` instead of swallowing them with a toast so failed syncs properly display the BSOD screen and log to `crash.log`.
4. **WebPortal Fix & Real LAN IP on Dashboard:**
   - Replace hardcoded `http://localhost:8080` in `DASH`, `NET_PROBE`, and `ifconfig` with the actual assigned LAN IP (`f"http://{self.get_ip()}:{self.config['web_port']}"` when connected, or `"OFFLINE"`).
   - Implement a non-blocking HTTP server (`socket.settimeout(0)` / `uselect`) inside `poll_webportal()` so the WebPortal reliably responds over Wi-Fi without locking Core 1 DMA, while keeping the `COM4` bridge relay compatible.
5. **BusyBox TCP `ping` & Network Discovery Toggle:**
   - Add a `ping <host> [port]` command to BusyBox (`run_busybox_cmd()`) that resolves DNS and measures TCP handshake round-trip latency (`ms`, default port `80` or `443`) across 4 probes (since RP2350 `lwIP` MicroPython does not expose raw ICMP sockets).
   - Add `"net_respond_ping": True` (and `"icmp_enabled"` config label) in Network Settings to toggle PinhOS's network discovery/echo responder on or off.
6. **Reload Animation & Soft-Reload Crash Fix:**
   - Fix `ACT:HOT_RELOAD` and the reload animation so exiting `run()` cleanly tears down `webportal`, frees `picocalc.pinhos`, runs `gc.collect()`, and re-enters `main.start()` via a safe outer loop in `main.py` without crashing.
7. **Fix `ACT:TEST_AUTH` Popup:**
   - Update `ACT:TEST_AUTH` so it forces `self.auth_modal` open regardless of `bridge_policy` (`TRUST` vs `AUTO`), allowing the 3-option authorization modal to be previewed anytime.
8. **GitHub OTA Pull & Bootloader UF2 Build Scripts:**
   - Implement real GitHub file manifest fetching in `perform_git_ota()` (pulling updated `.py`, theme, and web files over HTTPS into `/sd/pinhos/.staging/`, verifying downloads, atomically swapping them into `/sd/pinhos/`, and soft-rebooting).
   - Provide companion PC/WSL2 build scripts (`build_boot_uf2.sh` / `build_boot_uf2.ps1` + frozen `boot_stub.py`) capable of building both a standard minimal bootloader `.uf2` and an optional **`lv_micropython` + `picocalc` RP2350 `.uf2`** that auto-boots `/sd/pinhos/main.py`.

---

## Phase 2: Codebase Refactoring, SD Swap & Public Repo Cleanup
1. **Modularize `pinhos_os.py`:**
   - Split the monolith into a clean, public-ready package structure under `/sd/pinhos/`:
     - `main.py` (boot guard, 3-crash safe-mode fallback, clean reload loop)
     - `core/kernel.py` (`PinhOS` state machine, atomic config, breadcrumbs, BSOD)
     - `core/swap.py` (`SwapManager` cooperative state spilling + `SwapPager` windowed reader)
     - `core/bridge.py` (`<<PINHOS:...>>` UART protocol + isolated `RUN_APP:<path>` handler)
     - `core/sandbox.py` (isolated app runner, `sys.modules` snapshot/cleanup, `APP_META` parser)
     - `ui/renderer.py` (unified UI abstraction layer + native LUT renderer, partial redraws, modals, screensaver)
     - `ui/lvgl_backend.py` (optional LVGL display/input driver adapter with small RGB565 partial flush buffer + automatic exception/OOM fallback to `ui/renderer.py`)
     - `ui/themes.py` (backend-agnostic theme loader generating both 16-color RGB565 LUTs for Native mode and `lv.style_t` palettes for LVGL mode)
     - `ui/desktop.py` (optional Desktop Mode workspace supporting both Native and LVGL backends)
     - `net/manager.py` (Wi-Fi auto-connect/retry, scanner, NTP, TCP `ping`, GitHub OTA & Releases API)
     - `web/server.py` (non-blocking HTTP server, REST API, SD File Manager & dynamic theme CSS injection)
     - `apps/shell.py`, `apps/files.py`, `apps/store.py`, `apps/dev_studio.py`, `apps/toolkit.py`, `apps/hw_lab.py`
   - Update `picocalc.ps1` to recursively sync all folders/files cleanly to `/sd/pinhos/`.
2. **Modular & Theme-Synced WebPortal:**
   - Split `portal.html` into structured assets (`web/index.html`, `web/style.css`, `web/app.js`).
   - Serve dynamic CSS variables (`--bg`, `--fg`, `--accent`) derived from the active `ui/themes.py` palette so the WebPortal automatically matches the device's active theme regardless of Native or LVGL mode.
   - Add a live HTML5 `<canvas>` screen mirror + clickable virtual D-Pad/`F1`–`F10` controls powered by `get_portal_state_dict()`.
3. **Scrap Plugins — Standardize on Apps:**
   - Remove `VIEW:PLUGINS` and all "Plugins" terminology. Consolidate everything into **Apps** (`/sd/pinhos/apps`).
4. **GitHub Decoupling & Privacy Cleanup:**
   - Change default `git_repo` to `"PinhOS/PinhOS"` (official main repo).
   - Scrub personal/author names from all UI banners, modals, comments, and default strings—keep custom repository URL/branch overrides strictly inside Settings.

---

## Phase 3: Cyberdeck Field Toolkit & USB / SD Card Bridge
1. **Network Pocket Toolkit (BusyBox + Dedicated `NET TOOLKIT` View):**
   - **Wake-on-LAN (`wol <MAC>`):** Send UDP magic packets (`FF*6 + MAC*16`) on port `9` (plus saved MAC presets in `/sd/pinhos/wol_hosts.json`).
   - **TCP Port Scanner (`scan <host> [ports]`):** Non-blocking fast TCP port scanner (defaulting to common ports `21,22,23,53,80,443,445,3389,8080,8443` or custom ranges) with live open/closed progress readout.
   - **DNS Lookup (`nslookup <domain>`):** Resolve A records and display response latency.
2. **Serial UART Console (`minicom` / `screen` Mode):**
   - Add a full-screen **UART Serial Terminal** in Hardware Lab using the PicoCalc's exposed UART pins (`UART0` / `UART1`) to talk to routers, switches, ESP32s, or headless servers.
   - Support selectable baud rates (`9600`, `19200`, `38400`, `57600`, `115200`, `921600`), local echo toggle, CR/LF line-ending toggle, and optional session capture to `/sd/pinhos/serial_logs/`.
3. **USB Mass Storage & SD Card Transfer Bridge:**
   - **USB Mass Storage Mode (when supported by firmware `rp2` USB MSC):** Safely unmount `/sd` from MicroPython's VFS while active, expose the microSD card as a USB drive to the host PC, and cleanly remount `/sd` on exit.
   - **WebPortal & `COM4` SD File Manager Fallback:** Add full browse/upload/download/delete endpoints (`/api/fs/list`, `/api/fs/upload`, `/api/fs/download`, `/api/fs/delete`) in the WebPortal (over Wi-Fi HTTP and `COM4` bridge) so ROMs, themes, and logs can be transferred without removing the SD card even on standard MicroPython builds.
4. **PWM / Logic Signal Generator (Hardware Lab Upgrade):**
   - Extend Hardware Lab with a **PWM / Square-Wave Generator** allowing the user to select an available GPIO pin, frequency (`1 Hz` – `100 kHz`), and duty cycle (`0%` – `100%`) to test servos, buzzers, or breadboard circuits.
5. **Quick Scratchpad & Clipboard (`notes`):**
   - Add a lightweight plain-text/Markdown **Scratchpad** app saving to `/sd/pinhos/notes/` with a synced clipboard/notes panel in the WebPortal for copying IPs, pinouts, and commands between the PicoCalc and PC.
6. **Background Pomodoro / Alarm Timer:**
   - Add a background countdown/alarm service tied to `machine.RTC()` and the PWM buzzer (`Pin(26)`) that displays a subtle status badge in the top bar and chirps an alert regardless of which screen is open.

---

## Phase 4: App Developer Studio (On-Device & WebPortal)
1. **Dedicated On-Device `APP DEV STUDIO` Menu:**
   - Add an **App Developer Studio** submenu/view accessible from the Apps menu with:
     - **Quick-Start & Docs Viewer:** On-device cheat sheet showing how to structure a PinhOS app (`APP_META` schema, `picocalc.display` / `picocalc.keyboard` APIs, `ESC` exit convention), how to push over USB (`picocalc.ps1 hot_write`), and how to push over Wi-Fi WebPortal.
     - **Sandbox Live Tester:** List `.py` apps in `/sd/pinhos/apps/`, execute them inside `core/sandbox.py` (with automatic `SwapManager` memory spill before launch) with pre/post RAM delta readout (`KB used`), catch any traceback cleanly without crashing the OS, and display a crash summary modal if the test app fails.
     - **Generate App Template:** One-click scaffold generator creating a ready-to-edit boilerplate `.py` app with `APP_META` and an `ESC`-clean main loop in `/sd/pinhos/apps/`.
2. **WebPortal App Studio (Online Editor + Upload + Remote Run):**
   - Add an **App Studio** tab in the WebPortal (`web/index.html` + `web/app.js`) supporting both Wi-Fi HTTP endpoints and the `COM4` relay:
     - **Built-in Web Code Editor:** Lightweight monospace code editor in the browser that can load any existing `.py` app from `/sd/pinhos/apps/`, create a new one from a template, and save directly to the PicoCalc (`POST /api/apps/save`).
     - **File Upload Button:** Drag-and-drop or file-picker upload (`POST /api/apps/upload`) to push local `.py` files straight to `/sd/pinhos/apps/`.
     - **Remote Sandbox Run (`POST /api/apps/run`):** Trigger the uploaded/edited app immediately on the PicoCalc inside the isolated sandbox, capture/stream `print()` output and tracebacks back to a live output console in the WebPortal, and guarantee zero OS namespace pollution on exit.
3. **CLI Watch/Push Helper (`dev_watch.ps1`):**
   - Include a companion `dev_watch.ps1` script alongside `picocalc.ps1` that watches a local `.py` file on Windows and automatically runs `hot_write` + `<<PINHOS:RUN_APP:...>>` on file save for instant USB iteration.

---

## Phase 5: UI/UX, Dual-Backend Themes & Desktop Mode
1. **Configurable Graphics Backend (`NATIVE` vs `LVGL`) + Auto-Fallback:**
   - Add a **Graphics Engine (`NATIVE LUT` / `LVGL [BETA]`)** selector in Display Settings.
   - If `LVGL` is selected, trigger `SwapManager` spill first to maximize free heap, verify `lvgl` module availability and free heap (`>= 140 KB` free before init), mount the LVGL display flush driver, and show a confirmation toast; if LVGL is absent in firmware, low on RAM, or throws a runtime error, automatically fall back to `NATIVE LUT` and show an informative modal explaining why.
2. **Unified Custom Theme Engine & Git Theme Store (Compatible with Both Native & LVGL):**
   - Define external JSON theme schemas in `/sd/pinhos/themes/` (`name`, `colors` RGB palette, `layout`: `"LIST"` or `"MOSAIC"`, `border_radius`, `font_scale`) compiled by `ui/themes.py` into **both** a 16-color RGB565 LUT (for Native mode) and LVGL style objects (`lv.style_t` for LVGL mode) so every theme works identically on both renderers.
   - Add a `/themes` directory in the Git repo and a **Sync Themes from GitHub** option in Display Settings.
3. **Configurable Font Sizes (Console & System-Wide):**
   - Add `"ui_font_scale"` (`1x` / `1.25x` / `1.5x`) and `"term_font_scale"` (`1x` / `1.25x` / `1.5x`) in Display Settings with dynamic row/line wrapping (using bitmap scaling in Native mode and built-in Montserrat/unscii fonts in LVGL mode).
4. **Theme-Matched Animations & Progress Modals:**
   - Use the active theme's primary and background colors (`c_hi`, `c_bg`) for boot, reload, and `picocalc.ps1` update progress bars instead of hardcoded orange.
   - Add themed progress bars + explicit error popups for **Git Pull**, **NTP Sync**, and **App Store Sync**:
     - Render as a **centered modal dialog** for minor updates (NTP sync, App Store sync, single app install).
     - Render as a **full-screen overlay** for full OS OTA updates.
5. **Optional Desktop Mode:**
   - Add `"desktop_mode": False` in Settings (when enabled, boots directly into Desktop Mode by default, with a hotkey/Start button to switch back to the classic `DECK` menu).
   - Render a lightweight Linux/Windows-inspired desktop with app shortcut icons, a bottom taskbar + Start launcher, and mini system widgets (using LVGL widgets when active, or Native LUT primitives otherwise).
6. **Screensaver / LCD Burn-In Prevention:**
   - Add `"screensaver_sec"` (`OFF / 60s / 180s / 300s`). After idle timeout, launch a low-CPU animated screensaver (bouncing clock / Matrix rain / starfield) that wakes immediately on any key press.

---

## Phase 6: File Manager, App Metadata & F-Key Customization
1. **App Metadata & `F5` App Details Popup:**
   - Require a standard `APP_META = {"name": ..., "version": ..., "author": ..., "desc": ..., "ext": [...]}` header in every `/sd/pinhos/apps/*.py` file.
   - Pressing **`F5`** in the **App Menu** or **App Store** opens a Details/Options modal showing the app's metadata, version, author, and supported extensions.
2. **File Manager App Associations & `F5` File Details:**
   - Store extension-to-app mappings in `config.json` (e.g., `".nes": "nes_emu.py"`, `".mp3": "mp3_player.py"`, `".py": "__exec__"`).
   - Opening a file launches its associated app and passes the file path; if no app is mapped or installed for that extension, show a Windows-style **"Open With..."** app selection popup.
   - Pressing **`F5`** on a file in the File Manager opens a File Details/Options popup displaying file size, path, modified timestamp, and assigned default App (with an option to reassign it).
3. **Configurable `F1`–`F10` Keys & Page Auto-Reset:**
   - Support 2 pages of function keys in the footer bar (`Page 1: F1–F5`, `Page 2: F6–F10`).
   - Make all 10 `F`-keys user-remappable in Input Settings, including assigning a key to **Next F-Key Page**.
   - Add a configurable **F-Key Page Timeout** (with Enable/Disable toggle) that automatically resets the footer bar back to Page 1 after inactivity.

---

## Phase 7: Git Versioning, Logs, Power & Hardware Diagnostics
1. **Git Versioning, Release Browser & Instant Rollback Menu:**
   - **Local Version Archive (`/sd/pinhos/.versions/`):** Before applying any Git OTA update, automatically snapshot the active `/sd/pinhos/` codebase + `version.json` (tag, short commit SHA, timestamp, commit message) into `/sd/pinhos/.versions/<tag_or_sha>/` (retaining the last 5 versions on `/sd`).
   - **Versioning & Rollback Menu:** Add a dedicated menu under `OTA` showing the active version/SHA, cached local snapshots on `/sd`, and a 1-click offline **Rollback & Reboot** option.
   - **Remote GitHub Releases & Commits Browser:** Query `api.github.com/repos/<git_repo>/releases` and `/commits?per_page=8` (streaming via `SwapPager` to stay within RP2350 SRAM limits) to browse, install, or downgrade to any tagged release or commit SHA.
   - **3-Strike Safe-Mode & Auto-Rollback Guard (`breadcrumb.json`):** Track consecutive boot crashes in `/sd/pinhos/breadcrumb.json`. If 3 consecutive crashes occur within 15 seconds of boot, automatically force `ui_backend="NATIVE"`, `desktop_mode=False`, default `FLIPPER` theme, skip user auto-start scripts, and offer/trigger automatic rollback to the previous `.versions/` snapshot.
2. **Configurable Log Persistence & Retention:**
   - Add `"log_persistent": True` and `"log_retention_days": 7` in Log Settings. When persistence is `False`, wipe `system.log` on boot; when `True`, prune log entries older than the retention window on boot.
3. **Wi-Fi Auto-Connect & Retry Policy:**
   - Add `"wifi_autoconnect": True`, `"wifi_max_retries": 3`, and `"wifi_retry_sec": 5` in Network Settings, executing non-blocking retry attempts on boot when enabled.
4. **Detailed Battery & Power View:**
   - Add a dedicated **Battery & Power Details** screen parsing the PicoCalc STM32 PMU (`kb.battery()` / I2C `0x1F`) to show cell voltage, percentage, charging/discharging state, and estimated runtime.
5. **Power Button Single-Click Sleep:**
   - Inspect/poll the PicoCalc STM32 keyboard/PMU I2C status register (`0x1F`) for a short single-press power button event and route it to `enter_sleep_mode()` cleanly.
6. **Pinout & GPIO Inspector:**
   - Upgrade `VIEW:GPIO` into a full **Pinout & GPIO Inspector** displaying PicoCalc expansion header pin labels, mode (`IN`/`OUT`/`ADC`), live logic state (`HIGH`/`LOW`), and analog voltage readings.
7. **Framebuffer Screenshot (`F10` / `Ctrl+P`) & SD Storage Analyzer:**
   - Dump the 320x320 framebuffer directly to `/sd/pinhos/screenshots/scr_YYYYMMDD_HHMMSS.bmp` (downloadable in the WebPortal, supporting both Native LUT and LVGL RGB565 buffers) and show `/sd` storage usage bars in File Manager / System Info.
# Phase 5 OTA Authenticity, Atomic Rollback & TLS Heap Design (`Refs #21`)

> **Scope:** Design note and hardware TLS contiguous-heap spike only. No OTA downloader code is added here.

---

## 1. Why Same-Origin SHA-256 Is Insufficient
Fetching both a payload file (`*.mpy` / `*.py`) and its `sha256` manifest from the same origin (`raw.githubusercontent.com`) guarantees **transport/storage integrity** (detecting truncated writes or SD corruption) but **not authenticity**: an attacker who compromises the origin or performs a MITM/DNS hijack can replace both the file and its SHA-256 digest.

---

## 2. Authenticity Model (Two-Tier Path)

### Tier 1 (Phase 5 / `v1.0.0-alpha.5` — Immediate)
- **Signed Release Manifest (`ota_manifest.json` + `ota_manifest.sig`):**
  - Every GitHub Release tag (`v1.0.0-alpha.5`, etc.) is signed offline by the release maintainer using an Ed25519 keypair (or HMAC-SHA256 / ECDSA-P256 if constrained by MicroPython crypto primitives).
  - The **public verification key** is baked into the frozen UF2 (`firmware/frozen/`) so an attacker who only controls GitHub or the SD card cannot forge a manifest signature.
  - Every file entry in `ota_manifest.json` pins `{path, size, sha256}` AND the exact **git commit SHA + semver tag** (preventing downgrade attacks by rejecting `manifest.version <= current.version` unless `--force`).
- **Fallback if Ed25519 is not yet compiled into UF2:** Pin OTA fetches strictly to an immutable release **commit SHA** (verified against GitHub Releases API over TLS with certificate validation) until Ed25519 C `.mpy` / frozen module is added in `v1.1.0`.

---

## 3. Atomic A/B Staging & 3-Strike Boot Guard Rollback
1. **Stage:** Download all changed files into `/sd/pinhos/.ota_staging/<target_version>/` in `<= 1 KB` chunks (feeding WDT per chunk), verifying size + SHA-256 of every file before touching live files.
2. **Backup (A/B slot):** Move replaced live files into `/sd/pinhos/.ota_prev/` (single previous slot).
3. **Commit:** Rename staged files into `/sd/pinhos/...`, writing `/sd/pinhos/version.json` **last** so an interrupted swap never advertises the new version prematurely.
4. **Automatic Rollback:** Reboot into the new version. The existing **3-Strike Boot Guard** (`main.py` + `firmware/frozen/pinhos_boot.py`) increments `boot_strikes`. If the new release fails to reach 5s UI stabilization 3 times, Safe Recovery Mode offers 1-key rollback from `/sd/pinhos/.ota_prev/` (or auto-rolls back when `.ota_prev/` is present and `boot_strikes == 3`).

---

## 4. Clean-Heap "Updater Mode" (mbedTLS Contiguous-SRAM Budget)
`ssl.wrap_socket()` (mbedTLS) on RP2350 allocates ~24–40 KB of contiguous buffers for TLS record/handshake state. Under mid-session fragmentation (WebPortal + UI + tools), `largest_free` may drop below the TLS threshold even when total `gc.mem_free()` is >120 KB.

### Updater Mode Protocol (if TLS spike fails mid-session)
1. User selects **Settings → Check / Apply OTA Update**.
2. If `core.memutil.largest_free(96 * 1024) < TLS_MIN_BLOCK` (determined by the spike below), PinhOS writes `/sd/pinhos/ota_pending.json` (`{"action": "update", "target": ...}`) and calls `board.reboot()`.
3. On cold boot, `main.py` detects `ota_pending.json` **before** importing `ui.*`, `web.*`, or `tools.*` (~215 KB free, ~90+ KB contiguous!), runs the OTA download + verification + A/B swap with minimal framebuffer progress text, removes `ota_pending.json`, and reboots cleanly into the updated OS.

---

## 5. Hardware TLS Contiguous-Heap Spike (Run on PicoCalc)
Run on a connected PicoCalc to measure the exact `gc.mem_free()` and `largest_free(96*1024)` required for an HTTPS handshake to `raw.githubusercontent.com:443`:

```powershell
Set-Location C:\Users\BrunoPinho\Gemini_Workplace\pinhos
@"
import sys, gc, socket, ssl
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
from core.memutil import largest_free
gc.collect(); gc.collect()
print('PRE_TLS  free:', gc.mem_free(), 'largest_96k:', largest_free(96*1024))
s = socket.socket()
s.settimeout(5)
addr = socket.getaddrinfo('raw.githubusercontent.com', 443)[0][-1]
s.connect(addr)
ss = ssl.wrap_socket(s, server_hostname='raw.githubusercontent.com')
print('IN_TLS   free:', gc.mem_free(), 'largest_96k:', largest_free(96*1024))
ss.write(b'HEAD /bpinh0/PinhOS/main/version.json HTTP/1.0\r\nHost: raw.githubusercontent.com\r\n\r\n')
print('RESP:', ss.read(64))
ss.close()
gc.collect(); gc.collect()
print('POST_TLS free:', gc.mem_free(), 'largest_96k:', largest_free(96*1024))
"@ | Set-Content "$env:TEMP\spike_tls_21.py"
.\picocalc.ps1 raw "$env:TEMP\spike_tls_21.py"
```

Paste the `PRE_TLS` / `IN_TLS` / `POST_TLS` output into Issue `#21` to finalize `TLS_MIN_BLOCK`.

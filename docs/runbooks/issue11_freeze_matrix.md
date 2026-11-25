# Issue #11 — Hardware Freeze Reproduction Matrix Runbook

This runbook collects real RP2350 PicoCalc hardware data for **Issue #11** (`Net Probes` and `Wi-Fi Spectrum` across `menu` vs `POST /api/run`, `web on/off`, and `150 / 200 MHz`, **10 runs per cell**).

---

## 1. Deploy Branch & Run Stress Gates 13–14

```powershell
Set-Location <path-to-pinhos>
.\picocalc.ps1 test
```

Then run Stress Gates 13–14 and capture `gc.mem_free()` + `largest_free(96*1024)`:

```powershell
@"
import sys, gc
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
from core.memutil import largest_free
import tests.selftest_stress as ss
gc.collect()
print('BEFORE free:', gc.mem_free(), 'largest_96k:', largest_free(96*1024))
print('STRESS:', ss.run_stress())
gc.collect()
print('AFTER  free:', gc.mem_free(), 'largest_96k:', largest_free(96*1024))
"@ | Set-Content "$env:TEMP\run_stress_11.py"
.\picocalc.ps1 raw "$env:TEMP\run_stress_11.py"
```

---

## 2. Run the 16-Cell Freeze Reproduction Matrix (10 Runs / Cell)

### Setup per CPU frequency (`150` or `200` MHz)
1. Set CPU clock in **Settings → System, Power & Backup → CPU Clock Profile** (`150 MHz` or `200 MHz`) and reboot cleanly.
2. For **`web = on`** cells, enable **WebPortal IDE** (`6 → WebPortal IDE`), note the IP (`$PICO_IP`) and token (`$PICO_TOK`).
3. For **`POST /api/run`** cells, trigger each run from PowerShell (replace IP/token and target path `tools/net_tools.py` or `apps/wifi_spectrum.py`):

```powershell
$PICO_IP  = "192.168.1.93"
$PICO_TOK = "<8-char-token-from-picocalc>"
$TOOL     = "tools/net_tools.py"   # or "apps/wifi_spectrum.py"

for ($i = 1; $i -le 10; $i++) {
    $st0 = Invoke-RestMethod "http://${PICO_IP}:8080/api/status"
    Write-Host "[$i/10] BEFORE free=$($st0.sram_free) largest=$($st0.sram_largest)"
    Invoke-RestMethod -Method POST -Headers @{"X-PinhOS-Token"=$PICO_TOK} `
        "http://${PICO_IP}:8080/api/run?path=$TOOL" | Out-Null
    Read-Host "Run probe/scan on PicoCalc, press ESC to exit tool, then press Enter here"
    $st1 = Invoke-RestMethod "http://${PICO_IP}:8080/api/status"
    Write-Host "[$i/10] AFTER  free=$($st1.sram_free) largest=$($st1.sram_largest)"
}
```

If any run freezes, power-cycle the PicoCalc and capture `reset_cause` + `crash.log` tail:

```powershell
@"
import machine
print('reset_cause:', machine.reset_cause())
try:
    print(''.join(open('/sd/pinhos/logs/crash.log').readlines()[-12:]))
except Exception as e:
    print('no crash.log:', e)
"@ | Set-Content "$env:TEMP\chk_freeze.py"
.\picocalc.ps1 raw "$env:TEMP\chk_freeze.py"
```

---

## 3. Results Table (Paste Completed Table into Issue #11)

| # | Tool | Launch | Web | CPU MHz | Runs (Pass/10) | Freeze? | `reset_cause` | `largest_free` Before (B) | `largest_free` After (B) | Notes |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: | :--- | :-: | :-: | :--- |
| 1 | Net Probes | menu | off | 150 | /10 | | | | | |
| 2 | Net Probes | menu | on | 150 | /10 | | | | | |
| 3 | Net Probes | `/api/run` | on | 150 | /10 | | | | | |
| 4 | Net Probes | menu | off | 200 | /10 | | | | | |
| 5 | Net Probes | menu | on | 200 | /10 | | | | | |
| 6 | Net Probes | `/api/run` | on | 200 | /10 | | | | | |
| 7 | Wi-Fi Spectrum | menu | off | 150 | /10 | | | | | |
| 8 | Wi-Fi Spectrum | menu | on | 150 | /10 | | | | | |
| 9 | Wi-Fi Spectrum | `/api/run` | on | 150 | /10 | | | | | |
| 10 | Wi-Fi Spectrum | menu | off | 200 | /10 | | | | | |
| 11 | Wi-Fi Spectrum | menu | on | 200 | /10 | | | | | |
| 12 | Wi-Fi Spectrum | `/api/run` | on | 200 | /10 | | | | | |

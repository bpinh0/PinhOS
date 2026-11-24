# Issue #28 — Gate 15 Hardware Watchdog (`WDT_TIMEOUT`) Verification Runbook

Because `machine.WDT` performs a real RP2350 hardware reset (and is intentionally skipped when `serial_link` is active during USB REPL sessions), Gate 15 must be verified on a **standalone boot**.

## 1. Deploy Branch & Create Temporary Hang Applet

```powershell
Set-Location C:\Users\BrunoPinho\Gemini_Workplace\pinhos
git checkout fix/issue-28-wdt-coverage
.\picocalc.ps1 test
```

Upload a temporary deliberate-hang applet to `/sd/pinhos/apps/_gate15_hang.py`:

```powershell
@"
with open('/sd/pinhos/apps/_gate15_hang.py', 'w') as f:
    f.write("APP_META={'id':'gate15_hang','name':'Gate15 Hang','version':'1.0','category':'System','description':'WDT test','entry':'main','min_sram':16384,'ui_modes':['gui'],'native_libs':[]}\ndef main(ctx):\n    while True:\n        pass\n")
print('GATE15_APP_WRITTEN')
"@ | Set-Content "$env:TEMP\mk_g15.py"
.\picocalc.ps1 raw "$env:TEMP\mk_g15.py"
```

## 2. Standalone Boot & Trigger WDT Reset
1. Power-cycle the PicoCalc (standalone boot — do **not** press `CTRL+Q` / LNK).
2. Wait ~6s for Boot Guard stabilization; `WDT: Armed (8000ms)` is logged to `/sd/pinhos/logs/system.log`.
3. Open **`3 → Apps & Studio → Gate15 Hang`** (or `Wi-Fi Spectrum` first for 15s to confirm normal idle does **not** trip WDT).
4. Within ~8 seconds of launching `Gate15 Hang`, the RP2350 automatically hardware-resets and boots back into Desktop Home.

## 3. Capture Evidence (`system.log` + `crash.log`) & Clean Up

```powershell
@"
import os
print('=== SYSTEM.LOG (WDT) ===')
for ln in open('/sd/pinhos/logs/system.log'):
    if 'WDT' in ln: print(ln.strip())
print('=== CRASH.LOG (TAIL) ===')
print(''.join(open('/sd/pinhos/logs/crash.log').readlines()[-10:]))
try: os.remove('/sd/pinhos/apps/_gate15_hang.py')
except OSError: pass
"@ | Set-Content "$env:TEMP\chk_g15.py"
.\picocalc.ps1 raw "$env:TEMP\chk_g15.py"
```

Expected evidence in `crash.log`:
- `UNCLEAN SHUTDOWN in TOOL (Gate15 Hang) ... [WDT_TIMEOUT | ...KB]`

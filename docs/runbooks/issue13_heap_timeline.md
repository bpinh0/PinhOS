# Issue #13 — Cold-Boot Heap Retention & Fragmentation Timeline Runbook

## Root-Cause Note: Why First `WebServer START` Logs ~30–45 KB Lower Than `START` After `STOP`
In `web/server.py`, `start_async()` ran `gc.collect()` *before* `asyncio.start_server(...)`, then logged `gc.mem_free()` *after* `start_server()` without another `gc.collect()`. On the **first** start, importing `uasyncio` + `web.server` + binding the listener leaves ~30–45 KB of uncollected transient import/dict objects. When `stop_async()` runs `gc.collect()`, the **second** `START` logs with those modules already imported and GC'd (~30–45 KB higher). `#26` fixes the `START` telemetry to log post-`gc.collect()` free + `largest_free(96*1024)`.

## Hardware Timeline Capture Command
Run immediately after a clean power-cycle (press `Ctrl-C` on boot splash or run via `COM4`):

```powershell
Set-Location C:\Users\BrunoPinho\Gemini_Workplace\pinhos
@"
import sys, gc
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
from core.memutil import largest_free

def snap(stage):
    gc.collect(); gc.collect()
    print('| {} | {} | {} | {} | {} |'.format(
        stage, gc.mem_free(), gc.mem_alloc(), largest_free(96*1024), len(sys.modules)
    ))

print('| Stage | gc.mem_free (B) | gc.mem_alloc (B) | largest_free 96K (B) | sys.modules |')
print('| :--- | ---: | ---: | ---: | ---: |')
snap('1. Clean REPL')

from boards import get_board
from core.config import ConfigManager, load_version_manifest
from core.logger import get_logger
from core.theme import get_theme_manager
from ui.engine import UIEngine
b = get_board(); cfg = ConfigManager(); m = load_version_manifest()
lg = get_logger(); tm = get_theme_manager(config=cfg, board=b)
ui = UIEngine(board=b, theme_manager=tm, config=cfg)
snap('2. BOOT_OK + UIEngine')

from ui.desktop import DesktopHome
dh = DesktopHome(0, 20, 320, 256)
snap('3. Idle Desktop')

from net.wifi import get_wifi_manager, sync_ntp
wm = get_wifi_manager()
st = wm.status(force=True)
snap('4. Wi-Fi imported/status')

if st.get('connected'):
    sync_ntp(board=b, tz_offset_h=int(cfg.get('tz_offset_h', 0)), timeout_s=3)
    snap('5. After NTP sync')

from web.server import WebServer
ws = WebServer(board=b, config=cfg, manifest=m, host='0.0.0.0', port=8080)
ws.start()
snap('6. Web START (1st)')
ws.stop()
snap('7. Web STOP')
ws.start()
snap('8. Web START (2nd)')

from core.sandbox import SandboxRunner
sbx = SandboxRunner(board=b, config=cfg, theme=tm, ui=ui)
sbx.run_file('/sd/pinhos/apps/hello_world.py')
sbx = None
snap('9. After First Tool')
ws.stop()
"@ | Set-Content "$env:TEMP\timeline_13.py"
.\picocalc.ps1 raw "$env:TEMP\timeline_13.py"
```

Paste the resulting Markdown table directly into Issue `#13`.

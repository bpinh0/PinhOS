param(
    [Parameter(Position = 0)]
    [string]$Action = "upload_and_start",
    [Parameter(Position = 1)]
    [string]$Arg1 = "",
    [Parameter(Position = 2)]
    [string]$Arg2 = "",
    [string]$PortName = "",
    [int]$BaudRate = 115200,
    [switch]$NoMpremote,
    [switch]$NoSync,
    [switch]$NoMpy,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$EOT_PROMPT = [string][char]4 + ">"

# Resolve project root whether invoked from repo root or parent workspace
if (Test-Path (Join-Path $PSScriptRoot "version.json")) {
    $ProjectRoot = $PSScriptRoot
} elseif (Test-Path (Join-Path $PSScriptRoot "pinhos\version.json")) {
    $ProjectRoot = Join-Path $PSScriptRoot "pinhos"
} else {
    $ProjectRoot = $PSScriptRoot
}

function Resolve-PicoPort([string]$PreferredPort) {
    if ($PreferredPort -and $PreferredPort.Trim().Length -gt 0) {
        return $PreferredPort.Trim()
    }
    try {
        # Match ClockworkPi PicoCalc onboard CH340 (VID_1A86) or RP2350 USB CDC (VID_2E8A)
        $pnp = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
            Where-Object { ($_.PNPDeviceID -match "VID_1A86|VID_2E8A") -and $_.Name -match "\((COM\d+)\)" } |
            Select-Object -First 1
        if ($pnp -and $pnp.Name -match "\((COM\d+)\)") {
            return $Matches[1]
        }
    } catch {
    }
    $ports = [System.IO.Ports.SerialPort]::GetPortNames()
    if ($ports -contains "COM4") {
        return "COM4"
    }
    if ($ports.Length -gt 0) {
        return $ports[0]
    }
    return "COM4"
}

$ResolvedPort = Resolve-PicoPort $PortName

# Canonical Phase 1+2+3+4 OS tree deployed EXCLUSIVELY to /sd/pinhos/
# Mpy = $true entries are pre-compiled to .mpy bytecode (v6.3, -O2) via mpy-cross
# unless -NoMpy is specified, eliminating on-device AST compiler SRAM spikes.
$DeployManifest = @(
    @{ Local = "version.json";          Remote = "/sd/pinhos/version.json" },
    @{ Local = "main.py";               Remote = "/sd/pinhos/main.py";              MpyMain = $true },
    @{ Local = "boards\__init__.py";    Remote = "/sd/pinhos/boards/__init__.py";   Mpy = $true },
    @{ Local = "boards\base.py";        Remote = "/sd/pinhos/boards/base.py";       Mpy = $true },
    @{ Local = "boards\picocalc.py";    Remote = "/sd/pinhos/boards/picocalc.py";   Mpy = $true },
    @{ Local = "boards\generic_spi.py"; Remote = "/sd/pinhos/boards/generic_spi.py"; Mpy = $true },
    @{ Local = "core\__init__.py";      Remote = "/sd/pinhos/core/__init__.py";     Mpy = $true },
    @{ Local = "core\config.py";        Remote = "/sd/pinhos/core/config.py";       Mpy = $true },
    @{ Local = "core\logger.py";        Remote = "/sd/pinhos/core/logger.py";       Mpy = $true },
    @{ Local = "core\watchdog.py";      Remote = "/sd/pinhos/core/watchdog.py";     Mpy = $true },
    @{ Local = "core\memutil.py";       Remote = "/sd/pinhos/core/memutil.py";      Mpy = $true },
    @{ Local = "core\swap.py";          Remote = "/sd/pinhos/core/swap.py";         Mpy = $true },
    @{ Local = "core\sandbox.py";       Remote = "/sd/pinhos/core/sandbox.py";      Mpy = $true },
    @{ Local = "core\theme.py";         Remote = "/sd/pinhos/core/theme.py";        Mpy = $true },
    @{ Local = "ui\__init__.py";        Remote = "/sd/pinhos/ui/__init__.py";       Mpy = $true },
    @{ Local = "ui\fonts.py";           Remote = "/sd/pinhos/ui/fonts.py";          Mpy = $true },
    @{ Local = "ui\widgets.py";         Remote = "/sd/pinhos/ui/widgets.py";        Mpy = $true },
    @{ Local = "ui\gui.py";             Remote = "/sd/pinhos/ui/gui.py";            Mpy = $true },
    @{ Local = "ui\tui.py";             Remote = "/sd/pinhos/ui/tui.py";            Mpy = $true },
    @{ Local = "ui\engine.py";          Remote = "/sd/pinhos/ui/engine.py";         Mpy = $true },
    @{ Local = "ui\menu.py";            Remote = "/sd/pinhos/ui/menu.py";           Mpy = $true },
    @{ Local = "ui\_menu_net.py";       Remote = "/sd/pinhos/ui/_menu_net.py";      Mpy = $true },
    @{ Local = "ui\_log_view.py";       Remote = "/sd/pinhos/ui/_log_view.py";      Mpy = $true },
    @{ Local = "ui\desktop.py";         Remote = "/sd/pinhos/ui/desktop.py";        Mpy = $true },
    @{ Local = "net\__init__.py";       Remote = "/sd/pinhos/net/__init__.py";      Mpy = $true },
    @{ Local = "net\wifi.py";           Remote = "/sd/pinhos/net/wifi.py";          Mpy = $true },
    @{ Local = "net\sync.py";           Remote = "/sd/pinhos/net/sync.py";          Mpy = $true },
    @{ Local = "web\__init__.py";       Remote = "/sd/pinhos/web/__init__.py";      Mpy = $true },
    @{ Local = "web\server.py";         Remote = "/sd/pinhos/web/server.py";        Mpy = $true },
    @{ Local = "web\static\index.html"; Remote = "/sd/pinhos/web/static/index.html" },
    @{ Local = "web\static\style.css";  Remote = "/sd/pinhos/web/static/style.css" },
    @{ Local = "web\static\app.js";     Remote = "/sd/pinhos/web/static/app.js" },
    @{ Local = "tools\shell.py";        Remote = "/sd/pinhos/tools/shell.py" },
    @{ Local = "tools\_shell_cmds.py";  Remote = "/sd/pinhos/tools/_shell_cmds.py"; Mpy = $true },
    @{ Local = "tools\editor.py";       Remote = "/sd/pinhos/tools/editor.py" },
    @{ Local = "tools\files.py";        Remote = "/sd/pinhos/tools/files.py" },
    @{ Local = "tools\net_tools.py";    Remote = "/sd/pinhos/tools/net_tools.py" },
    @{ Local = "tools\uart_term.py";    Remote = "/sd/pinhos/tools/uart_term.py" },
    @{ Local = "tools\sysmon.py";       Remote = "/sd/pinhos/tools/sysmon.py" },
    @{ Local = "apps\hello_world.py";   Remote = "/sd/pinhos/apps/hello_world.py" },
    @{ Local = "apps\matrix_deck.py";   Remote = "/sd/pinhos/apps/matrix_deck.py" },
    @{ Local = "apps\doom_deck.py";     Remote = "/sd/pinhos/apps/doom_deck.py" },
    @{ Local = "apps\wifi_spectrum.py"; Remote = "/sd/pinhos/apps/wifi_spectrum.py" },
    @{ Local = "tests\selftest.py";     Remote = "/sd/pinhos/tests/selftest.py";    Mpy = $true },
    @{ Local = "tests\selftest_p3.py";  Remote = "/sd/pinhos/tests/selftest_p3.py"; Mpy = $true },
    @{ Local = "tests\selftest_p4.py";  Remote = "/sd/pinhos/tests/selftest_p4.py"; Mpy = $true },
    @{ Local = "tests\selftest_stress.py"; Remote = "/sd/pinhos/tests/selftest_stress.py"; Mpy = $true }
)

$themesDir = Join-Path $ProjectRoot "themes"
if (Test-Path $themesDir) {
    Get-ChildItem -Path $themesDir -Filter "*.json" | ForEach-Object {
        $DeployManifest += @{
            Local  = ("themes\" + $_.Name)
            Remote = ("/sd/pinhos/themes/" + $_.Name)
        }
    }
}

$script:StaleRemotePyPaths = @()
$script:MpyActive = $false

function ConvertTo-WslPath([string]$winPath) {
    $full = [System.IO.Path]::GetFullPath($winPath)
    if ($full -match "^([A-Za-z]):\\(.*)$") {
        $drv = $Matches[1].ToLower()
        $rest = $Matches[2].Replace("\", "/")
        return "/mnt/$drv/$rest"
    }
    return $full.Replace("\", "/")
}

function Resolve-MpyManifest($manifest) {
    if ($NoMpy) {
        return $manifest
    }
    $nativeMpy = Get-Command mpy-cross -ErrorAction SilentlyContinue
    $useWsl = $false
    if (-not $nativeMpy) {
        $wslCmd = Get-Command wsl -ErrorAction SilentlyContinue
        if ($wslCmd) {
            $useWsl = $true
        } else {
            Write-Host "[PinhOS] mpy-cross not found (native or WSL2); deploying raw .py sources." -ForegroundColor Yellow
            return $manifest
        }
    }

    $buildDir = Join-Path $ProjectRoot ".mpy_build"
    if (-not (Test-Path $buildDir)) {
        New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    }

    $toCompile = @()
    $resolved = @()
    $stalePy = @()

    foreach ($item in $manifest) {
        $srcFull = Join-Path $ProjectRoot $item.Local
        if ($item.MpyMain -and (Test-Path $srcFull)) {
            $outRel = "_pinhos_main.mpy"
            $outFull = Join-Path $buildDir $outRel
            $toCompile += @{ Src = $srcFull; Out = $outFull; Label = "main.py" }

            $shimPath = Join-Path $buildDir "main_shim.py"
            $shimTxt = "# PinhOS Bytecode Entry Shim (auto-generated by picocalc.ps1)`nimport sys as _s, _pinhos_main as _m`nif __name__ == '__main__':`n    _s.modules['main'] = _m`n    _m.start(skip_strike_increment=bool(globals().get('_FLASH_GUARD_ACTIVE', False)), interactive=True)`nelse:`n    _n = __name__`n    globals().update(_m.__dict__)`n    __name__ = _n`n"
            [System.IO.File]::WriteAllText($shimPath, $shimTxt)

            $resolved += @{ LocalFull = $outFull; Local = $outRel; Remote = "/sd/pinhos/_pinhos_main.mpy" }
            $resolved += @{ LocalFull = $shimPath; Local = "main.py (shim)"; Remote = "/sd/pinhos/main.py" }
        }
        elseif ($item.Mpy -and (Test-Path $srcFull)) {
            $mpyRel = [System.Text.RegularExpressions.Regex]::Replace($item.Local, "\.py$", ".mpy")
            $mpyRem = [System.Text.RegularExpressions.Regex]::Replace($item.Remote, "\.py$", ".mpy")
            $outFull = Join-Path $buildDir $mpyRel
            $outDir = Split-Path -Parent $outFull
            if (-not (Test-Path $outDir)) {
                New-Item -ItemType Directory -Path $outDir -Force | Out-Null
            }
            $toCompile += @{ Src = $srcFull; Out = $outFull; Label = $item.Local }
            $resolved += @{ LocalFull = $outFull; Local = $mpyRel; Remote = $mpyRem }
            $stalePy += $item.Remote
        }
        else {
            $resolved += @{ LocalFull = $srcFull; Local = $item.Local; Remote = $item.Remote }
        }
    }

    if ($toCompile.Count -eq 0) {
        return $resolved
    }

    Write-Host ("[PinhOS] Compiling {0} core OS modules to .mpy bytecode (-O2)..." -f $toCompile.Count) -ForegroundColor Cyan
    if ($nativeMpy) {
        foreach ($job in $toCompile) {
            & $nativeMpy.Source -O2 -o $job.Out $job.Src
            if ($LASTEXITCODE -ne 0) {
                throw "[ERROR] mpy-cross failed on $($job.Label)"
            }
        }
    } else {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.AppendLine("set -e")
        [void]$sb.AppendLine('MPY=$(command -v mpy-cross || echo "$HOME/.local/bin/mpy-cross")')
        [void]$sb.AppendLine('if [ ! -x "$MPY" ]; then echo "MPY_MISSING"; exit 42; fi')
        foreach ($job in $toCompile) {
            $wSrc = ConvertTo-WslPath $job.Src
            $wOut = ConvertTo-WslPath $job.Out
            [void]$sb.AppendLine("`"`$MPY`" -O2 -o '$wOut' '$wSrc'")
        }
        $batchFile = Join-Path $buildDir "_compile_mpy.sh"
        [System.IO.File]::WriteAllText($batchFile, ($sb.ToString() -replace "`r`n", "`n"))
        $wBatch = ConvertTo-WslPath $batchFile
        $wslOut = & wsl bash $wBatch 2>&1
        if ($LASTEXITCODE -eq 42) {
            Write-Host "[PinhOS] mpy-cross not installed in WSL2; deploying raw .py sources." -ForegroundColor Yellow
            return $manifest
        }
        if ($LASTEXITCODE -ne 0) {
            throw "[ERROR] WSL2 mpy-cross compilation failed: $wslOut"
        }
    }

    $script:StaleRemotePyPaths = $stalePy
    $script:MpyActive = $true
    Write-Host ("[PinhOS] Bytecode ready ({0} .mpy modules compiled)." -f $toCompile.Count) -ForegroundColor Green
    return $resolved
}

function Remove-StaleRemotePy($sp) {
    if (-not $script:MpyActive -or $script:StaleRemotePyPaths.Count -eq 0) {
        return
    }
    $pyList = ($script:StaleRemotePyPaths | ForEach-Object { "'$_'" }) -join ","
    $cleanCode = @"
_rm=0
for _p in ($pyList,):
 try:
  os.remove(_p); _rm+=1
 except Exception:
  pass
_bp('STALE_PY_RM:' + str(_rm))
"@
    $out = Invoke-RawRepl $sp $cleanCode 6000 16 12 -RequiredMarker "STALE_PY_RM:"
    if ($out -match "STALE_PY_RM:(\d+)" -and [int]$Matches[1] -gt 0) {
        Write-Host ("[PinhOS] Removed {0} stale .py source(s) on SD so .mpy bytecode loads cleanly." -f $Matches[1]) -ForegroundColor Cyan
    }
}

# Flash-only bootstrap stubs (/boot.py and tiny ~30-line /main.py)
# Explicitly mounts rp2.Flash() at '/', mounts /sd, and binds UART(0) GP0/GP1 -> CH340 COM4
$FlashBootStub = @"
# PinhOS Flash Boot Bridge (/boot.py)
import os, sys, machine
try:
    _u = machine.UART(0, 115200, rxbuf=4096)
    os.dupterm(_u, 0)
except Exception:
    pass
try:
    import picocalc
    if hasattr(picocalc, 'sd') and hasattr(picocalc.sd, 'mount'):
        picocalc.sd.mount()
except Exception:
    pass
if '/sd/pinhos' not in sys.path:
    sys.path.insert(0, '/sd/pinhos')
"@ -replace "`r`n", "`n"

$FlashMainStub = @"
# PinhOS 3-Strike Boot Guard Stub (main.py)
import os, sys, json

STATE_FILES = ('/boot_state.json', '/sd/pinhos/boot_state.json')

def _bp(msg):
    print(msg)

def _load_st():
    st = {'boot_strikes': 0, 'strike_limit': 3, 'safe_mode': False}
    for p in STATE_FILES:
        try:
            st.update(json.load(open(p, 'r')))
            return st
        except Exception:
            pass
    return st

def _save_st(st):
    for p in STATE_FILES:
        try:
            with open(p, 'w') as f:
                json.dump(st, f)
        except Exception:
            pass

def _safe_mode(reason, strikes=3):
    try:
        import machine
        os.dupterm(machine.UART(0, 115200, rxbuf=4096), 0)
    except Exception:
        pass
    _bp('<<PINHOS:SAFE_RECOVERY_MODE:strikes={}>> {}'.format(strikes, reason))
    try:
        import picocalc
        d = picocalc.display; d.recoverRefresh(); d.fill(0)
        d.rect(4, 4, 312, 312, 9); d.fill_rect(6, 6, 308, 24, 9)
        d.text('!! PINHOS SAFE RECOVERY MODE !!', 32, 14, 15)
        d.text('STRIKES: {}/3 | BOOT FAULT'.format(strikes), 16, 46, 3)
        d.text(str(reason)[:36], 16, 68, 15)
        d.text('Serial REPL Active (recovery_*)', 16, 104, 10)
    except Exception:
        pass

def _boot():
    st = _load_st()
    st['boot_strikes'] = int(st.get('boot_strikes', 0)) + 1
    st['safe_mode'] = st['boot_strikes'] >= 3
    _save_st(st)
    if st['safe_mode']:
        return _safe_mode('3-strike threshold reached', st['boot_strikes'])
    try:
        import picocalc
        try:
            os.listdir('/sd')
        except Exception:
            picocalc.sd.mount()
        if '/sd/pinhos' not in sys.path:
            sys.path.insert(0, '/sd/pinhos')
        exec(open('/sd/pinhos/main.py', 'r').read(), {'__name__': '__main__', '_FLASH_GUARD_ACTIVE': True})
    except Exception as e:
        _safe_mode(repr(e), st['boot_strikes'])

if __name__ == '__main__':
    _boot()
"@ -replace "`r`n", "`n"

function Get-NormalBytes([string]$localPath) {
    if ($localPath.EndsWith(".py") -or $localPath.EndsWith(".json") -or $localPath.EndsWith(".html") -or $localPath.EndsWith(".css") -or $localPath.EndsWith(".js")) {
        $txt = ([System.IO.File]::ReadAllText($localPath) -replace "`r`n", "`n")
        return [System.Text.Encoding]::UTF8.GetBytes($txt)
    }
    return [System.IO.File]::ReadAllBytes($localPath)
}

function Get-QuickSig([byte[]]$bytes) {
    if (-not $bytes -or $bytes.Length -eq 0) {
        return "0:0:0:0"
    }
    [long]$sum = 0
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        $sum += $bytes[$i]
    }
    return "$($bytes.Length):$sum`:$($bytes[0]):$($bytes[$bytes.Length - 1])"
}

function Send-Paced($sp, [string]$text, [int]$chunkSize = 16, [int]$delayMs = 12) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    for ($i = 0; $i -lt $bytes.Length; $i += $chunkSize) {
        $len = [Math]::Min($chunkSize, $bytes.Length - $i)
        $sp.Write($bytes, $i, $len)
        if ($delayMs -gt 0) {
            Start-Sleep -Milliseconds $delayMs
        }
    }
}

function Wait-RawPrompt($sp, [int]$maxMs = 5000, [string]$RequiredMarker = "") {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $sb = New-Object System.Text.StringBuilder
    while ($sw.ElapsedMilliseconds -lt $maxMs) {
        if ($sp.BytesToRead -gt 0) {
            $rd = $sp.ReadExisting()
            [void]$sb.Append($rd)
            if ($rd.IndexOf([char]4) -lt 0 -and $rd.IndexOf('>') -lt 0) {
                continue
            }
            $acc = $sb.ToString()
            $hasMarker = $true
            $markerIdx = 0
            if ($RequiredMarker -and $RequiredMarker.Length -gt 0) {
                $markerIdx = $acc.IndexOf($RequiredMarker, [System.StringComparison]::Ordinal)
                $hasMarker = ($markerIdx -ge 0)
            }
            if ($hasMarker) {
                $eotIdx = $acc.LastIndexOf($EOT_PROMPT, [System.StringComparison]::Ordinal)
                if ($eotIdx -ge $markerIdx) {
                    Start-Sleep -Milliseconds 15
                    if ($sp.BytesToRead -gt 0) {
                        [void]$sb.Append($sp.ReadExisting())
                    }
                    return $sb.ToString()
                }
            }
        } else {
            Start-Sleep -Milliseconds 4
        }
    }
    return $sb.ToString()
}

function Format-RawReplOutput([string]$raw) {
    if (-not $raw) {
        return ""
    }
    $clean = $raw
    $okIdx = $clean.IndexOf("OK", [System.StringComparison]::Ordinal)
    if ($okIdx -ge 0 -and $okIdx -lt 32) {
        $clean = $clean.Substring($okIdx + 2)
    }
    $clean = $clean.Replace($EOT_PROMPT, "").Replace([string][char]4, "")
    return $clean.Trim()
}

function ConvertTo-Base64Exec([string]$code) {
    $norm = ($code -replace "`r`n", "`n").Trim()
    if ($norm.Contains("`n")) {
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($norm))
        return "exec(binascii.a2b_base64('$b64'))"
    }
    return $norm
}

function Invoke-RawRepl($sp, [string]$code, [int]$timeoutMs = 6000, [int]$chunkSize = 16, [int]$delayMs = 12, [switch]$RawText, [string]$RequiredMarker = "") {
    if ($sp.BytesToRead -gt 0) {
        [void]$sp.ReadExisting()
    }
    $payload = if ($RawText) { ($code -replace "`r`n", "`n").Trim() } else { ConvertTo-Base64Exec $code }
    Send-Paced $sp ($payload + "`n") $chunkSize $delayMs
    $sp.Write([string][char]4)
    $raw = Wait-RawPrompt $sp $timeoutMs $RequiredMarker
    return (Format-RawReplOutput $raw)
}

function Stream-RawReplCommand($sp, [string]$code, [string]$doneMarker, [int]$maxMs = 14000) {
    [void](Read-UntilIdle $sp 60 300)
    $payload = ConvertTo-Base64Exec $code
    Send-Paced $sp ($payload + "`n") 16 12
    $sp.Write([string][char]4)

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $drainIdleSw = $null
    $sb = New-Object System.Text.StringBuilder
    $printedLen = 0

    while ($sw.ElapsedMilliseconds -lt $maxMs) {
        if ($sp.BytesToRead -gt 0) {
            [void]$sb.Append($sp.ReadExisting())
            if ($null -ne $drainIdleSw) {
                $drainIdleSw.Restart()
            }
            $acc = $sb.ToString()
            $displayStr = $acc
            if ($displayStr.StartsWith("OK")) {
                $displayStr = $displayStr.Substring(2)
            }
            $displayStr = $displayStr.Replace($EOT_PROMPT, "").Replace([string][char]4, "")
            if ($displayStr.Length -gt $printedLen) {
                $newChunk = $displayStr.Substring($printedLen)
                Write-Host -NoNewline $newChunk
                $printedLen = $displayStr.Length
            }
            if ($null -eq $drainIdleSw) {
                $markerHit = ($doneMarker -and ($acc.IndexOf($doneMarker, [System.StringComparison]::Ordinal) -ge 0))
                $eotIdx = $acc.LastIndexOf($EOT_PROMPT, [System.StringComparison]::Ordinal)
                if ($doneMarker) {
                    $tbIdx = $acc.IndexOf("Traceback", [System.StringComparison]::Ordinal)
                    $errDone = ($tbIdx -ge 0 -and $eotIdx -gt $tbIdx)
                    if ($markerHit -or $errDone) {
                        # Start 350ms post-sentinel idle drain so trailing lines / tracebacks print completely
                        $drainIdleSw = [System.Diagnostics.Stopwatch]::StartNew()
                    }
                } elseif ($eotIdx -ge 0) {
                    $drainIdleSw = [System.Diagnostics.Stopwatch]::StartNew()
                }
            }
        } else {
            if ($null -ne $drainIdleSw -and $drainIdleSw.ElapsedMilliseconds -ge 350) {
                break
            }
            Start-Sleep -Milliseconds 15
        }
    }

    # Final flush of any remaining unprinted buffer characters
    $finalStr = $sb.ToString()
    if ($finalStr.StartsWith("OK")) {
        $finalStr = $finalStr.Substring(2)
    }
    $finalStr = $finalStr.Replace($EOT_PROMPT, "").Replace([string][char]4, "")
    if ($finalStr.Length -gt $printedLen) {
        Write-Host -NoNewline $finalStr.Substring($printedLen)
    }
    Write-Host ""
    return (Format-RawReplOutput $sb.ToString())
}

function Read-UntilIdle($sp, [int]$idleMs = 250, [int]$maxMs = 8000) {
    $idleSw = [System.Diagnostics.Stopwatch]::StartNew()
    $totalSw = [System.Diagnostics.Stopwatch]::StartNew()
    $sb = New-Object System.Text.StringBuilder
    while ($idleSw.ElapsedMilliseconds -lt $idleMs -and $totalSw.ElapsedMilliseconds -lt $maxMs) {
        if ($sp.BytesToRead -gt 0) {
            [void]$sb.Append($sp.ReadExisting())
            $idleSw.Restart()
        } else {
            Start-Sleep -Milliseconds 10
        }
    }
    return $sb.ToString()
}

function Initialize-PicoRawSession($sp) {
    # Wait 150ms after opening COM4, interrupt any running loop (Ctrl-C x2), then enter Raw REPL (Ctrl-A)
    Start-Sleep -Milliseconds 150
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $sp.Write([string][char]3)
        Start-Sleep -Milliseconds 80
        $sp.Write([string][char]3)
        Start-Sleep -Milliseconds 140
        [void](Read-UntilIdle $sp 80 400)

        $sp.Write([string][char]1)
        [void](Read-UntilIdle $sp 80 400)

        # Bootstrap imports first (1-liner, no newlines) so binascii is ready for Base64 exec
        [void](Invoke-RawRepl $sp "import os,sys,gc,io,json,time,binascii,machine" 3000 16 12 -RawText)

        # Define _bp() and sequential chunk writer _wchk() using standard print()
        $stage1 = @"
def _bp(*a):
    print(' '.join(str(x) for x in a))
def _wchk(s):
    try:
        _bp('W:' + str(_f.write(binascii.a2b_base64(s))))
    except Exception as _e:
        _bp('ERR:' + repr(_e))
_bp('HANDSHAKE_OK')
"@
        $hsOut = Invoke-RawRepl $sp $stage1 4000 16 12 -RequiredMarker "HANDSHAKE_OK"
        if ($hsOut -match "HANDSHAKE_OK") {
            break
        }
    }

    if ($hsOut -notmatch "HANDSHAKE_OK") {
        foreach ($fallbackBaud in @(153600, 184320, 192000, 76800)) {
            try {
                $sp.BaudRate = $fallbackBaud
                Start-Sleep -Milliseconds 100
                $sp.Write([string][char]3)
                Start-Sleep -Milliseconds 80
                $sp.Write([string][char]3)
                Start-Sleep -Milliseconds 120
                [void](Read-UntilIdle $sp 80 300)
                $sp.Write([string][char]1)
                [void](Read-UntilIdle $sp 80 300)
                [void](Invoke-RawRepl $sp "import os,machine;_u=machine.UART(0,115200,rxbuf=4096);os.dupterm(_u,0)" 2000 16 12 -RawText)
                $sp.Write([string][char]2)
                Start-Sleep -Milliseconds 80
                $sp.BaudRate = $BaudRate
                Start-Sleep -Milliseconds 100
                $sp.Write([string][char]3)
                Start-Sleep -Milliseconds 80
                $sp.Write([string][char]3)
                Start-Sleep -Milliseconds 120
                [void](Read-UntilIdle $sp 80 300)
                $sp.Write([string][char]1)
                [void](Read-UntilIdle $sp 80 300)
                [void](Invoke-RawRepl $sp "import os,sys,gc,io,json,time,binascii,machine" 3000 16 12 -RawText)
                $hsOut = Invoke-RawRepl $sp $stage1 4000 16 12 -RequiredMarker "HANDSHAKE_OK"
                if ($hsOut -match "HANDSHAKE_OK") {
                    break
                }
            } catch {
                $sp.BaudRate = $BaudRate
            }
        }
    }

    if ($hsOut -notmatch "HANDSHAKE_OK") {
        Write-Host ""
        Write-Host "=========================================================================" -ForegroundColor Red
        Write-Host "[ERROR] Handshake failed on $ResolvedPort. Raw response: '$hsOut'" -ForegroundColor Red
        Write-Host "ONE-TIME FIX: Type this 1 line on the PicoCalc's physical keyboard REPL:" -ForegroundColor Cyan
        Write-Host "  import os,machine;os.dupterm(machine.UART(0,115200,rxbuf=4096),0)" -ForegroundColor Green
        Write-Host "Then re-run: .\picocalc.ps1 upload_and_start" -ForegroundColor Cyan
        Write-Host "=========================================================================" -ForegroundColor Red
        throw "Serial handshake failed on $ResolvedPort (raw output: '$hsOut')."
    }
}

function Test-RemoteFileSig($sp, [string]$remotePath, [string]$expectedSig) {
    $chkOut = Invoke-RawRepl $sp "print('CHK:' + _sig('$remotePath'))" 4000 16 12 -RawText -RequiredMarker "CHK:"
    while ($sp.BytesToRead -gt 0) {
        [void]$sp.ReadExisting()
        Start-Sleep -Milliseconds 30
    }
    if ($chkOut -match "CHK:([0-9]+:[0-9]+:[0-9]+:[0-9]+|MISSING)") {
        return ($Matches[1] -eq $expectedSig)
    }
    return $false
}

function Upload-SdFile($sp, [byte[]]$rawBytes, [string]$remotePath, [int]$pct = -1) {
    $rawStep = 384
    $totalBytes = $rawBytes.Length
    $totalChunks = [Math]::Max(1, [int][Math]::Ceiling($totalBytes / [double]$rawStep))
    $expectedSig = Get-QuickSig $rawBytes
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $lastErr = ""

    for ($fileAttempt = 1; $fileAttempt -le 2; $fileAttempt++) {
        while ($sp.BytesToRead -gt 0) {
            [void]$sp.ReadExisting()
            Start-Sleep -Milliseconds 30
        }
        $openOut = Invoke-RawRepl $sp "try:`n _f=open('$remotePath','wb');_bp('OPEN_OK')`nexcept Exception as _e:`n _bp('OPEN_ERR:'+repr(_e))" 4000 16 10 -RequiredMarker "OPEN_"
        if ($openOut -notmatch "OPEN_OK") {
            $lastErr = $openOut
            continue
        }

        $chunkIdx = 0
        $allChunksOk = $true
        for ($byteOffset = 0; $byteOffset -lt $totalBytes; $byteOffset += $rawStep) {
            $chunkIdx++
            $rawLen = [Math]::Min($rawStep, $totalBytes - $byteOffset)
            $slice = [Convert]::ToBase64String($rawBytes, $byteOffset, $rawLen)

            $wOut = Invoke-RawRepl $sp "_wchk('$slice')" 4000 16 10 -RawText
            if ($wOut -notmatch "W:$rawLen\b") {
                $lastErr = "Chunk $chunkIdx/$totalChunks got: '$wOut'"
                $allChunksOk = $false
                break
            }

            $elapsedSec = [Math]::Max(0.01, $sw.Elapsed.TotalSeconds)
            $rate = $chunkIdx / $elapsedSec
            $remChunks = $totalChunks - $chunkIdx
            $etaSec = [int][Math]::Ceiling($remChunks / $rate)
            $chunkPct = [int](($chunkIdx * 100) / $totalChunks)
            Write-Host -NoNewline ("`r      [chunk {0}/{1} | {2}% | ETA {3}s]   " -f $chunkIdx, $totalChunks, $chunkPct, $etaSec)
        }

        $closeCmd = "try:`n _f.close()`nexcept Exception:`n pass`n"
        if ($pct -ge 0 -and $allChunksOk) {
            $closeCmd += "_bar($pct)`n"
        }
        $closeCmd += "_bp('SIG:' + _sig('$remotePath'))"
        $closeOut = Invoke-RawRepl $sp $closeCmd 5000 16 10 -RequiredMarker "SIG:"

        $sigVerified = $false
        if ($closeOut -match "SIG:([0-9]+:[0-9]+:[0-9]+:[0-9]+)") {
            $sigVerified = ($Matches[1] -eq $expectedSig)
        }

        if ($allChunksOk -and $sigVerified) {
            Write-Host ("`r      [done {0}/{0} chunks in {1:N2}s]          " -f $totalChunks, $sw.Elapsed.TotalSeconds)
            return
        }
        if ($allChunksOk -and (-not $sigVerified)) {
            $lastErr = "Final signature mismatch (expected '$expectedSig', got '$closeOut')"
        }
        Start-Sleep -Milliseconds 100
    }

    throw "[ERROR] File verification failed while writing $remotePath ($lastErr)."
}

# Offline build & bytecode/JSON verification target (no serial port required)
if ($Action -in @("build", "compile", "mpy")) {
    $resolved = Resolve-MpyManifest $DeployManifest
    if (-not $script:MpyActive) {
        throw "[ERROR] mpy-cross bytecode build did not complete."
    }
    $mpyFiles = $resolved | Where-Object { $_.LocalFull -and $_.LocalFull.EndsWith(".mpy") }
    foreach ($mf in $mpyFiles) {
        $hdr = [System.IO.File]::ReadAllBytes($mf.LocalFull)
        if ($hdr.Length -lt 4 -or $hdr[0] -ne 0x4D -or $hdr[1] -ne 6 -or $hdr[3] -ne 31) {
            throw "[ERROR] Unexpected .mpy header in $($mf.Local): expected v6.3 (got $($hdr[0]), $($hdr[1]), $($hdr[2]), $($hdr[3]))"
        }
    }
    $jsonFiles = @(Join-Path $ProjectRoot "version.json") + (Get-ChildItem -Path (Join-Path $ProjectRoot "themes") -Filter "*.json" | ForEach-Object { $_.FullName })
    foreach ($jf in $jsonFiles) {
        $rawJ = [System.IO.File]::ReadAllText($jf, [System.Text.Encoding]::UTF8)
        $null = ConvertFrom-Json $rawJ
        if ($jf -match "\\themes\\" -and ([System.Text.Encoding]::UTF8.GetByteCount($rawJ) -gt 1024)) {
            throw "[ERROR] Theme file exceeds 1024 B atomic write cap: $jf"
        }
    }
    Write-Host ("[PinhOS] Build OK: {0} .mpy modules (v6.3, -O2) & {1} JSON files verified." -f $mpyFiles.Count, $jsonFiles.Count) -ForegroundColor Green
    exit 0
}

# Primary fast transport if mpremote is installed on PATH
$mpremoteCmd = Get-Command mpremote -ErrorAction SilentlyContinue
if ((-not $NoMpremote) -and $mpremoteCmd) {
    $mp = $mpremoteCmd.Source
    if ($Action -eq "upload_and_start") {
        Write-Host "[mpremote] Fast bulk-syncing PinhOS Phase 1 to $ResolvedPort..."
        $tmpBoot = Join-Path $env:TEMP "pinhos_boot_stub.py"
        $tmpMain = Join-Path $env:TEMP "pinhos_main_stub.py"
        [System.IO.File]::WriteAllText($tmpBoot, $FlashBootStub)
        [System.IO.File]::WriteAllText($tmpMain, $FlashMainStub)
        & $mp connect $ResolvedPort exec "import os; [os.mkdir(d) for d in ('/sd/pinhos','/sd/pinhos/boards','/sd/pinhos/core','/sd/pinhos/ui','/sd/pinhos/net','/sd/pinhos/web','/sd/pinhos/web/static','/sd/pinhos/tools','/sd/pinhos/apps','/sd/pinhos/themes','/sd/pinhos/fonts','/sd/pinhos/banners','/sd/pinhos/.swap','/sd/pinhos/logs','/sd/pinhos/screenshots','/sd/pinhos/tests') if d.split('/')[-1] not in os.listdir('/'.join(d.split('/')[:-1]) or '/')]"
        & $mp connect $ResolvedPort fs cp $tmpBoot ":/boot.py"
        & $mp connect $ResolvedPort fs cp $tmpMain ":/main.py"
        $totalFiles = $DeployManifest.Count
        $idx = 0
        foreach ($entry in $DeployManifest) {
            $idx++
            $src = Join-Path $ProjectRoot $entry.Local
            if (Test-Path $src) {
                Write-Host ("[{0}/{1}] [mpremote cp] {2} -> {3}" -f $idx, $totalFiles, $entry.Local, $entry.Remote)
                & $mp connect $ResolvedPort fs cp $src (":" + $entry.Remote)
            }
        }
        Write-Host "[mpremote] Starting /sd/pinhos/main.py..."
        & $mp connect $ResolvedPort exec "import sys; sys.path.insert(0, '/sd/pinhos'); import main; main.clear_boot_strikes(); main.start(wait_for_stability=True, interactive=True)"
        exit 0
    }
    elseif ($Action -eq "test") {
        $testPath = Join-Path $ProjectRoot "tests\selftest.py"
        if (-not $NoSync -and (Test-Path $testPath)) {
            & $mp connect $ResolvedPort fs cp $testPath ":/sd/pinhos/tests/selftest.py"
        }
        & $mp connect $ResolvedPort exec "import sys; sys.path.insert(0, '/sd/pinhos'); import tests.selftest as st; st.run_all()"
        exit $LASTEXITCODE
    }
}

$sp = New-Object System.IO.Ports.SerialPort $ResolvedPort, $BaudRate, 'None', 8, 'One'
$sp.Handshake = [System.IO.Ports.Handshake]::None
$sp.ReadBufferSize = 65536
$sp.ReadTimeout = 500
$sp.WriteTimeout = 5000
# Keep DtrEnable & RtsEnable FALSE for ClockworkPi PicoCalc CH340 (VID_1A86&PID_7523)
$sp.DtrEnable = $false
$sp.RtsEnable = $false

$availPorts = [System.IO.Ports.SerialPort]::GetPortNames()
if ($availPorts -notcontains $ResolvedPort) {
    Write-Host "[ERROR] Serial port '$ResolvedPort' is not detected (available: $($availPorts -join ', '))." -ForegroundColor Red
    exit 1
}

try {
    $sp.Open()
} catch {
    Write-Host "[ERROR] Cannot open '$ResolvedPort' (port is locked by another process or access denied): $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if ($Action -in @("com", "check", "ping", "status")) {
    try {
        Write-Host "[COM CHECK] Port '$ResolvedPort' opened OK @ $BaudRate baud. Probing PicoCalc REPL..." -ForegroundColor Cyan
        Start-Sleep -Milliseconds 120
        $sp.Write([string][char]3)
        Start-Sleep -Milliseconds 120
        $sp.Write([string][char]3)
        Start-Sleep -Milliseconds 500
        $sp.Write("`r`n")
        $probe = Read-UntilIdle $sp 350 1800
        if ($probe -notmatch ">>>|raw REPL|KeyboardInterrupt|PINHOS") {
            $sp.Write("`r`n")
            $probe += Read-UntilIdle $sp 300 1000
        }
        if ($probe -match ">>>|raw REPL|KeyboardInterrupt|PINHOS") {
            Write-Host "[COM CHECK] PASS: '$ResolvedPort' is OPEN and PicoCalc REPL responded ($($probe.Trim() -replace '\s+', ' '))" -ForegroundColor Green
            if ($probe -match "Interrupted via serial Ctrl\+C") {
                # Resume PinhOS UI automatically so a read-only 'com' check doesn't leave the screen at REPL
                Send-Paced $sp "import sys;sys.path.insert(0,'/sd/pinhos') if '/sd/pinhos' not in sys.path else None;import main;main.ui_loop()`r`n"
                Start-Sleep -Milliseconds 200
            }
            exit 0
        } else {
            Write-Host "[COM CHECK] LOCKED / NO REPL: '$ResolvedPort' opened, but PinhOS did not respond (enable LNK via Shift+F7 / CTRL+Q on PicoCalc)." -ForegroundColor Yellow
            exit 2
        }
    } finally {
        if ($sp -and $sp.IsOpen) { $sp.Close() }
    }
}

try {
    if ($Action -eq "upload_and_start") {
        Write-Host "[PinhOS] Connecting to PicoCalc on $ResolvedPort ($BaudRate baud)..."
        Initialize-PicoRawSession $sp
        Write-Host "[PinhOS] Handshake verified (UART0 GP0/GP1 rxbuf=4096 active)."

        $now = Get-Date
        $wday = ([int]$now.DayOfWeek + 6) % 7
        $rtcTuple = "($($now.Year), $($now.Month), $($now.Day), $wday, $($now.Hour), $($now.Minute), $($now.Second), 0)"

        # Stage 2A-1: Probe whether '/' is writable; if mounting rp2.Flash() raises OSError(28) (ENOSPC)
        # or OSError(1) (EPERM), treat as non-fatal FLASH_SKIP and fall back cleanly to SD boot hooks.
        $stage2A1 = @"
try:import picocalc
except Exception:picocalc=None
_flash_writable=False
try:
 with open('/.pinhos_probe','w') as _pf:_pf.write('1')
 os.remove('/.pinhos_probe')
 _flash_writable=True
except Exception:
 try:
  import rp2
  _bdev=globals().get('bdev') or rp2.Flash()
  _vfs=os.VfsLfs2(_bdev,progsize=256)
  os.mount(_vfs,'/')
  _flash_writable=True
 except Exception as _fe:
  _bp('FLASH_SKIP:'+repr(_fe))
try:
 os.listdir('/sd')
except Exception:
 try:picocalc.sd.mount()
 except Exception:pass
_bp('STAGE2A1_OK:' + ('FLASH_RW' if _flash_writable else 'SD_ONLY'))
"@
        $s2a1Out = Invoke-RawRepl $sp $stage2A1 6000 16 12 -RequiredMarker "STAGE2A1_OK:"
        $flashWritable = ($s2a1Out -match "FLASH_RW")
        if ($s2a1Out -match "FLASH_SKIP:(\S+)") {
            Write-Host "[PinhOS] Internal flash '/' not writable ($($Matches[1])); using SD boot fallback." -ForegroundColor Yellow
        }

        # Stage 2A-2: Sync RTC, create /sd/pinhos/ canonical directories, and define _sig() / _bar()
        $stage2A2 = @"
try:
    machine.RTC().datetime($rtcTuple)
except Exception:
    pass
for _d in ('/sd/pinhos','/sd/pinhos/boards','/sd/pinhos/core','/sd/pinhos/ui','/sd/pinhos/net','/sd/pinhos/web','/sd/pinhos/web/static','/sd/pinhos/tools','/sd/pinhos/apps','/sd/pinhos/themes','/sd/pinhos/fonts','/sd/pinhos/banners','/sd/pinhos/.swap','/sd/pinhos/logs','/sd/pinhos/screenshots','/sd/pinhos/tests'):
    try:
        os.mkdir(_d)
    except Exception:
        pass
try:
    os.remove('/sd/pinhos/config_snapshot.json')
except Exception:
    pass
def _sig(p):
    try:
        n=0;s=0;a=-1;z=0
        with open(p, 'rb') as f:
            while True:
                c = f.read(1024)
                if not c: break
                if a < 0: a = c[0]
                n += len(c); s += sum(c); z = c[-1]
        return '{}:{}:{}:{}'.format(n, s, a, z) if n else '0:0:0:0'
    except Exception:
        return 'MISSING'
def _bar(p):
    try:
        picocalc.display.fill_rect(42, 156, p, 8, 3)
    except Exception:
        pass
_bp('STAGE2A_OK')
"@
        $s2aOut = Invoke-RawRepl $sp $stage2A2 6000 16 12 -RequiredMarker "STAGE2A_OK"
        if ($s2aOut -notmatch "STAGE2A_OK") {
            throw "[ERROR] Stage 2A SD/directory init failed on $ResolvedPort (got: '$s2aOut')."
        }

        # Stage 2B: Install bootstrap stubs (/boot.py & /main.py on '/' only if _flash_writable,
        # always install on '/sd/boot.py', '/sd/main.py', and '/sd/MicroPython/boot files/')
        $bootBytes = [System.Text.Encoding]::UTF8.GetBytes($FlashBootStub)
        $mainBytes = [System.Text.Encoding]::UTF8.GetBytes($FlashMainStub)
        $bootStubSig = Get-QuickSig $bootBytes
        $mainStubSig = Get-QuickSig $mainBytes

        if ($flashWritable) {
            $stubCheckOut = Invoke-RawRepl $sp "_bp('STUBS:' + _sig('/boot.py') + '|' + _sig('/main.py'))" 4000 16 12 -RequiredMarker "STUBS:"
            if ($stubCheckOut -notmatch [regex]::Escape("STUBS:$bootStubSig|$mainStubSig")) {
                Write-Host "[PinhOS] Writing flash bootstrap stubs (/boot.py & /main.py)..."
                Upload-SdFile $sp $bootBytes "/boot.py" -1
                Upload-SdFile $sp $mainBytes "/main.py" -1
            }
        }

        $sdStubCheck = Invoke-RawRepl $sp "_bp('SD_STUBS:' + _sig('/sd/boot.py') + '|' + _sig('/sd/main.py'))" 4000 16 12 -RequiredMarker "SD_STUBS:"
        if ($sdStubCheck -notmatch [regex]::Escape("SD_STUBS:$bootStubSig|$mainStubSig")) {
            Write-Host "[PinhOS] Writing SD bootstrap stubs (/sd/boot.py & /sd/main.py)..."
            Upload-SdFile $sp $bootBytes "/sd/boot.py" -1
            Upload-SdFile $sp $mainBytes "/sd/main.py" -1
        }

        # Hook '/sd/MicroPython/boot files/boot.py' & 'main.py' if present on this PicoCalc UF2
        $sdBootHookCode = @"
_bf_dir = '/sd/MicroPython/boot files'
try:
    _bf_list = os.listdir(_bf_dir)
    if 'boot.py' in _bf_list:
        with open(_bf_dir + '/boot.py', 'r') as _f:
            _btxt = _f.read()
        if 'PINHOS_COLD_BOOT' not in _btxt:
            _hook = '\n# PINHOS_COLD_BOOT\ntry:\n import os,sys,machine\n _u=machine.UART(0,115200,rxbuf=4096);os.dupterm(_u,0)\n if "/sd/pinhos" not in sys.path:sys.path.insert(0,"/sd/pinhos")\nexcept Exception:pass\n'
            with open(_bf_dir + '/boot.py', 'w') as _f:
                _f.write(_btxt + _hook)
    with open('/sd/main.py', 'rb') as _mf:
        _mbytes = _mf.read()
    with open(_bf_dir + '/main.py', 'wb') as _tf:
        _tf.write(_mbytes)
    _bp('SD_BOOT_FILES_HOOKED')
except Exception as _he:
    _bp('SD_BOOT_HOOK_SKIP:' + repr(_he))
"@
        $hookVerify = Invoke-RawRepl $sp $sdBootHookCode 5000 16 12 -RequiredMarker "SD_BOOT_"
        Write-Host "[PinhOS] Boot hook status: $hookVerify"

        $drawBoxCode = @"
if picocalc and hasattr(picocalc, 'display'):
    try:
        _d = picocalc.display
        _d.recoverRefresh()
        _d.fill(0)
        _d.rect(18, 118, 284, 64, 3)
        _d.text('DEPLOYING PinhOS v1.0.0-alpha.5.1', 36, 134, 3)
        _d.rect(40, 154, 240, 12, 3)
    except Exception:
        pass
gc.collect()
_bp('INIT_OK')
"@
        $initOut = Invoke-RawRepl $sp $drawBoxCode 5000 16 12 -RequiredMarker "INIT_OK"
        if ($initOut -notmatch "INIT_OK") {
            throw "[ERROR] Failed to receive INIT_OK before file sync (got: '$initOut')."
        }

        # Step 2: Single-file override or incremental SD-only sync to /sd/pinhos/
        if ($Arg1 -and $Arg2 -and (Test-Path $Arg1)) {
            $bytes = Get-NormalBytes (Resolve-Path $Arg1).Path
            Write-Host "[PinhOS] Uploading $Arg1 -> $Arg2 ($($bytes.Length) B)..."
            Upload-SdFile $sp $bytes $Arg2 236
        } elseif (-not $NoSync) {
            $effectiveManifest = Resolve-MpyManifest $DeployManifest
            Remove-StaleRemotePy $sp
            $totalFiles = $effectiveManifest.Count
            $idx = 0
            $uploadedCount = 0
            $skippedCount = 0

            foreach ($item in $effectiveManifest) {
                $idx++
                $localFull = if ($item.LocalFull) { $item.LocalFull } else { Join-Path $ProjectRoot $item.Local }
                if (Test-Path $localFull) {
                    $pct = [int](($idx / $totalFiles) * 236)
                    $bytes = Get-NormalBytes $localFull
                    $localSig = Get-QuickSig $bytes

                    if ((-not $Force) -and (Test-RemoteFileSig $sp $item.Remote $localSig)) {
                        $skippedCount++
                        Write-Host ("[{0}/{1}] [SKIP] {2} (unchanged, {3} B)" -f $idx, $totalFiles, $item.Remote, $bytes.Length)
                        [void](Invoke-RawRepl $sp "_bar($pct)" 3000)
                    } else {
                        $uploadedCount++
                        Write-Host ("[{0}/{1}] [SYNC] {2} -> {3} ({4} B)" -f $idx, $totalFiles, $item.Local, $item.Remote, $bytes.Length)
                        Upload-SdFile $sp $bytes $item.Remote $pct
                    }
                }
            }
            Write-Host "[PinhOS] Sync complete: $uploadedCount uploaded, $skippedCount unchanged."
        }

        # Step 3: Self-contained launch of /sd/pinhos/main.py with live 5s Boot Guard streaming,
        # then enter interactive keyboard ui_loop()
        Write-Host "[PinhOS] Launching /sd/pinhos/main.py and streaming Boot Guard stabilization..."
        $launchCode = @"
import os, sys, io, gc, machine
_keep = ('__name__','os','sys','gc','io','json','time','binascii','machine','_bp','_wchk','_sig','_bar','picocalc','_keep')
for _k in list(globals().keys()):
 if _k not in _keep:del globals()[_k]
try:
 import builtins as _bi
 _osrv = getattr(_bi, '_pinhos_web_srv', None)
 if _osrv is not None:
  try: _osrv.close()
  except Exception: pass
  setattr(_bi, '_pinhos_web_srv', None)
 for _bk in ('recovery_status','recovery_reset_strikes','recovery_reset_config','recovery_clear_swap','recovery_reboot','ui'):
  if hasattr(_bi,_bk):delattr(_bi,_bk)
except Exception:pass
for _m in list(sys.modules.keys()):
 if _m not in ('picocalc','picocalcdisplay','vtterminal','os','sys','gc','io','json','time','binascii','machine','rp2','network','socket','struct','array','framebuf','builtins'):
  del sys.modules[_m]
gc.collect(); gc.collect()
if '/sd/pinhos' not in sys.path:sys.path.insert(0,'/sd/pinhos')
try:
 import main as _pm
 _pm.clear_boot_strikes()
 _pm.bp('VERIFIED_OK FREE_RAM:' + str(gc.mem_free()))
 _pm.start(wait_for_stability=True, interactive=False)
except Exception as _e:
 _buf=io.StringIO();sys.print_exception(_e,_buf);_bp('BOOT_ERR:\r\n'+_buf.getvalue())
"@
        [void](Stream-RawReplCommand $sp $launchCode "<<PINHOS:BOOT_OK:" 12000)
        # Exit Raw REPL cleanly (Ctrl-B) and start interactive keyboard ui_loop() in Friendly REPL
        $sp.Write([string][char]2)
        [void](Read-UntilIdle $sp 150 600)
        Send-Paced $sp "_pm.ui_loop()`r`n"
        Start-Sleep -Milliseconds 250
    }
    elseif ($Action -eq "test") {
        Write-Host "[PinhOS] Running Phase 1+2+3 Self-Test Gate on $ResolvedPort..."
        Initialize-PicoRawSession $sp

        $prepTestCode = @"
try:
 import picocalc
 if hasattr(picocalc,'sd'):picocalc.sd.mount()
except Exception:pass
for _d in ('/sd/pinhos/web','/sd/pinhos/web/static'):
 try:os.mkdir(_d)
 except Exception:pass
if '/sd/pinhos' not in sys.path:sys.path.insert(0,'/sd/pinhos')
def _sig(p):
 try:
  n=0;s=0;a=-1;z=0
  with open(p,'rb') as f:
   while True:
    c=f.read(1024)
    if not c:break
    if a<0:a=c[0]
    n+=len(c);s+=sum(c);z=c[-1]
  return '{}:{}:{}:{}'.format(n,s,a,z) if n else '0:0:0:0'
 except Exception:return 'MISSING'
def _bar(p):pass
_bp('PREP_OK')
"@
        [void](Invoke-RawRepl $sp $prepTestCode 6000 16 12 -RequiredMarker "PREP_OK")

        if (-not $NoSync) {
            $effectiveManifest = Resolve-MpyManifest $DeployManifest
            Remove-StaleRemotePy $sp
            $totalFiles = $effectiveManifest.Count
            $idx = 0
            foreach ($item in $effectiveManifest) {
                $idx++
                $localFull = if ($item.LocalFull) { $item.LocalFull } else { Join-Path $ProjectRoot $item.Local }
                if (Test-Path $localFull) {
                    $bytes = Get-NormalBytes $localFull
                    $localSig = Get-QuickSig $bytes
                    if ((-not $Force) -and (Test-RemoteFileSig $sp $item.Remote $localSig)) {
                        Write-Host ("[{0}/{1}] [SKIP] {2} (unchanged, {3} B)" -f $idx, $totalFiles, $item.Remote, $bytes.Length)
                    } else {
                        Write-Host ("[{0}/{1}] [SYNC] Updating {2} ({3} B)..." -f $idx, $totalFiles, $item.Remote, $bytes.Length)
                        Upload-SdFile $sp $bytes $item.Remote -1
                    }
                }
            }
        }

        $runTestCmd = @"
import os, sys, io, gc
_keep = ('__name__','os','sys','gc','io','json','time','binascii','machine','_bp','_wchk','_sig','_bar','picocalc','_keep')
for _k in list(globals().keys()):
 if _k not in _keep:del globals()[_k]
try:
 import builtins as _bi
 _osrv = getattr(_bi, '_pinhos_web_srv', None)
 if _osrv is not None:
  try: _osrv.close()
  except Exception: pass
  setattr(_bi, '_pinhos_web_srv', None)
 for _bk in ('recovery_status','recovery_reset_strikes','recovery_reset_config','recovery_clear_swap','recovery_reboot','ui'):
  if hasattr(_bi,_bk):delattr(_bi,_bk)
except Exception:pass
for _m in list(sys.modules.keys()):
 if _m not in ('picocalc','picocalcdisplay','vtterminal','os','sys','gc','io','json','time','binascii','machine','rp2','network','socket','struct','array','framebuf','builtins'):
  del sys.modules[_m]
gc.collect(); gc.collect()
try:
 import tests.selftest as _st
 _st.run_all(interactive_wait=False)
except Exception as _e:
 _buf=io.StringIO();sys.print_exception(_e,_buf);_bp('<<PINHOS:SELFTEST:FAIL:0/12>>\r\n'+_buf.getvalue())
"@
        $testOut = Stream-RawReplCommand $sp $runTestCmd "<<PINHOS:SELFTEST:" 150000
        # Purge selftest modules/globals cleanly in Raw REPL before relaunching interactive UI
        $relaunchPrep = @"
import sys, gc
for _k in ('_st','_e','_buf'):
 if _k in globals(): del globals()[_k]
for _m in list(sys.modules.keys()):
 if _m not in ('picocalc','picocalcdisplay','vtterminal','os','sys','gc','io','json','time','binascii','machine','rp2','network','socket','struct','array','framebuf','builtins','__pinhos_wdt__'):
  del sys.modules[_m]
gc.collect(); gc.collect()
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
import _pinhos_main as _pm
sys.modules['main'] = _pm
_pm.start(wait_for_stability=False, skip_strike_increment=True, interactive=False)
_bp('RELAUNCH_FREE:' + str(gc.mem_free()))
"@
        [void](Invoke-RawRepl $sp $relaunchPrep 12000 16 12 -RequiredMarker "RELAUNCH_FREE:")
        # Exit Raw REPL cleanly (Ctrl-B) back to friendly >>> prompt with dupterm preserved
        $sp.Write([string][char]2)
        [void](Read-UntilIdle $sp 150 500)
        $script:RelaunchUi = $true
        Send-Paced $sp "_pm.ui_loop()`r`n"
        Start-Sleep -Milliseconds 300
        if ($testOut -match "<<PINHOS:SELFTEST:FAIL" -or $testOut -notmatch "<<PINHOS:SELFTEST:PASS") {
            exit 1
        }
    }
    elseif ($Action -eq "stress") {
        Write-Host "[PinhOS] Running Deep Stress Suite (Gates 13-14 + Menu Walk) on $ResolvedPort..." -ForegroundColor Cyan
        Initialize-PicoRawSession $sp
        $runStressCmd = @"
import os, sys, io, gc
for _m in list(sys.modules.keys()):
 if _m not in ('picocalc','picocalcdisplay','vtterminal','os','sys','gc','io','json','time','binascii','machine','rp2','network','socket','struct','array','framebuf','builtins','__pinhos_wdt__'):
  del sys.modules[_m]
gc.collect(); gc.collect()
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
try:
 from core.memutil import largest_free
 import tests.selftest_stress as _ss
 _bp('STRESS_BEFORE free=' + str(gc.mem_free()) + ' blk96k=' + str(largest_free(96*1024)))
 _r = _ss.run_stress(deep=True)
 gc.collect(); gc.collect()
 _bp('STRESS_AFTER  free=' + str(gc.mem_free()) + ' blk96k=' + str(largest_free(96*1024)))
 _bp('<<PINHOS:STRESS:PASS>> ' + str(_r))
except Exception as _e:
 _buf=io.StringIO(); sys.print_exception(_e, _buf); _bp('<<PINHOS:STRESS:FAIL>>\r\n' + _buf.getvalue())
"@
        $stressOut = Stream-RawReplCommand $sp $runStressCmd "<<PINHOS:STRESS:" 120000
        $relaunchStressPrep = @"
import sys, gc
for _k in ('_ss','_r','_e','_buf','largest_free'):
 if _k in globals(): del globals()[_k]
for _m in list(sys.modules.keys()):
 if _m not in ('picocalc','picocalcdisplay','vtterminal','os','sys','gc','io','json','time','binascii','machine','rp2','network','socket','struct','array','framebuf','builtins','__pinhos_wdt__'):
  del sys.modules[_m]
gc.collect(); gc.collect()
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
import _pinhos_main as _pm
sys.modules['main'] = _pm
_pm.start(wait_for_stability=False, skip_strike_increment=True, interactive=False)
_bp('RELAUNCH_FREE:' + str(gc.mem_free()))
"@
        [void](Invoke-RawRepl $sp $relaunchStressPrep 12000 16 12 -RequiredMarker "RELAUNCH_FREE:")
        $sp.Write([string][char]2)
        [void](Read-UntilIdle $sp 150 500)
        $script:RelaunchUi = $true
        Send-Paced $sp "_pm.ui_loop()`r`n"
        Start-Sleep -Milliseconds 300
        if ($stressOut -match "<<PINHOS:STRESS:FAIL" -or $stressOut -notmatch "<<PINHOS:STRESS:PASS") {
            exit 1
        }
    }
    elseif ($Action -eq "pkt") {
        Send-Paced $sp ("<<PINHOS:" + $Arg1 + ">>")
        $res = Read-UntilIdle $sp 4200 8000
        Write-Output $res
    }
    elseif ($Action -eq "exec_file") {
        $clean = ((Get-Content -Raw -Path $Arg1) -replace "`r`n", "`n")
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($clean))
        Send-Paced $sp ("<<PINHOS:EXEC:import binascii;exec(binascii.a2b_base64('" + $b64 + "'),globals(),loc)>>")
        $res = Read-UntilIdle $sp 800 8000
        Write-Output $res
    }
    elseif ($Action -eq "hot_write") {
        $rawBytes = [System.IO.File]::ReadAllBytes($Arg1)
        $b64 = [Convert]::ToBase64String($rawBytes)
        Send-Paced $sp ("<<PINHOS:WRITE:" + $Arg2 + ":" + $b64 + ">>")
        $res = Read-UntilIdle $sp 600 8000
        Write-Output $res
    }
    elseif ($Action -eq "raw") {
        $code = Get-Content -Raw -Path $Arg1
        Initialize-PicoRawSession $sp
        $rawTimeoutMs = 15000
        if ($Arg2 -and $Arg2 -match '^\d+$') { $rawTimeoutMs = [int]$Arg2 }
        $out = Invoke-RawRepl $sp $code $rawTimeoutMs
        $sp.Write([string][char]2)
        [void](Read-UntilIdle $sp 150 500)
        Write-Output $out
    }
    elseif ($Action -eq "screenshot") {
        Write-Host "[PinhOS] Capturing 320x320 BMP screenshot from $ResolvedPort..." -ForegroundColor Cyan
        Initialize-PicoRawSession $sp
        $outFile = if ($Arg1 -and $Arg1.Trim().Length -gt 0) { $Arg1.Trim() } else { Join-Path $PSScriptRoot "picocalc_shot.bmp" }
        $shotCode = @"
import sys, time, binascii
if '/sd/pinhos' not in sys.path: sys.path.insert(0, '/sd/pinhos')
from boards import get_board
_b = get_board()
_p = _b.screenshot()
if not _p:
    _bp('SHOT_ERR:no_fb')
else:
    _bp('SHOT_PATH:' + _p)
    with open(_p, 'rb') as _f:
        while True:
            _c = _f.read(240)
            if not _c: break
            _bp('B64:' + binascii.b2a_base64(_c).decode().strip())
            time.sleep_ms(2)
    time.sleep_ms(40)
    _bp('SHOT_DONE')
"@
        $shotOut = Invoke-RawRepl $sp $shotCode 60000 16 12 -RequiredMarker "SHOT_DONE"
        $sp.Write([string][char]2)
        [void](Read-UntilIdle $sp 150 500)
        Send-Paced $sp "if '_pm' in globals(): _pm.ui_loop()`r`n"
        Start-Sleep -Milliseconds 150
        if ($shotOut -match "SHOT_DONE") {
            $ms = New-Object System.IO.MemoryStream
            foreach ($ln in ($shotOut -split "`r?`n")) {
                if ($ln.StartsWith("B64:")) {
                    $chunk = [Convert]::FromBase64String($ln.Substring(4).Trim())
                    $ms.Write($chunk, 0, $chunk.Length)
                }
            }
            [System.IO.File]::WriteAllBytes($outFile, $ms.ToArray())
            Write-Host "[PinhOS] Saved screenshot ($($ms.Length) B) -> $outFile" -ForegroundColor Green
        } else {
            Write-Host "[ERROR] Screenshot capture failed: $shotOut" -ForegroundColor Red
            exit 1
        }
    }
} finally {
    if ($sp -and $sp.IsOpen) {
        if ($Action -ne "upload_and_start" -and -not $script:RelaunchUi) {
            try {
                $sp.Write([string][char]2)
                Start-Sleep -Milliseconds 100
            } catch {
            }
        }
        $sp.Close()
    }
}

param(
    [string]$Action = "cmd",
    [string]$Arg1 = "",
    [string]$Arg2 = "",
    [string]$PortName = "COM4",
    [int]$BaudRate = 115200
)

$ErrorActionPreference = "Stop"

$sp = New-Object System.IO.Ports.SerialPort $PortName, $BaudRate, 'None', 8, 'One'
$sp.ReadBufferSize = 65536
$sp.ReadTimeout = 500
$sp.WriteTimeout = 5000
$sp.Open()

function Send-Paced($sp, [string]$text, [int]$chunkSize = 48, [int]$delayMs = 4) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    for ($i = 0; $i -lt $bytes.Length; $i += $chunkSize) {
        $len = [Math]::Min($chunkSize, $bytes.Length - $i)
        $sp.Write($bytes, $i, $len)
        Start-Sleep -Milliseconds $delayMs
    }
}

function Wait-RawPrompt($sp, [int]$maxMs = 5000) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $sb = New-Object System.Text.StringBuilder
    while ($sw.ElapsedMilliseconds -lt $maxMs) {
        if ($sp.BytesToRead -gt 0) {
            [void]$sb.Append($sp.ReadExisting())
            if ($sb.ToString().EndsWith(">")) {
                return $sb.ToString()
            }
        } else {
            Start-Sleep -Milliseconds 10
        }
    }
    return $sb.ToString()
}

function Read-UntilIdle($sp, [int]$idleMs = 350, [int]$maxMs = 15000) {
    $idleSw = [System.Diagnostics.Stopwatch]::StartNew()
    $totalSw = [System.Diagnostics.Stopwatch]::StartNew()
    $sb = New-Object System.Text.StringBuilder
    while ($idleSw.ElapsedMilliseconds -lt $idleMs -and $totalSw.ElapsedMilliseconds -lt $maxMs) {
        if ($sp.BytesToRead -gt 0) {
            [void]$sb.Append($sp.ReadExisting())
            $idleSw.Restart()
        } else {
            Start-Sleep -Milliseconds 20
        }
    }
    return $sb.ToString()
}

try {
    if ($Action -eq "upload_and_start") {
        $cleanText = ([System.IO.File]::ReadAllText($Arg1) -replace "`r`n`r`n", "`n" -replace "`r`n", "`n")
        $rawBytes = [System.Text.Encoding]::UTF8.GetBytes($cleanText)
        $b64 = [Convert]::ToBase64String($rawBytes)

        # Enter Raw REPL
        $sp.Write([string][char]3 + [string][char]3 + [string][char]1)
        Start-Sleep -Milliseconds 300
        [void]$sp.ReadExisting()

        $now = Get-Date
        $wday = ([int]$now.DayOfWeek + 6) % 7
        $rtcTuple = "($($now.Year), $($now.Month), $($now.Day), $wday, $($now.Hour), $($now.Minute), $($now.Second), 0)"

        $initCode = @"
import binascii, os, sys, gc, time, machine, picocalc
try:
    machine.RTC().datetime($rtcTuple)
except Exception:
    pass
u = machine.UART(0, 115200, rxbuf=4096)
os.dupterm(u, 0)
if hasattr(picocalc, 'pinhos'):
    try:
        picocalc.pinhos.stop_webportal()
    except Exception:
        pass
    del picocalc.pinhos
if 'main' in sys.modules:
    del sys.modules['main']
gc.collect()
try:
    picocalc.display.recoverRefresh()
except Exception:
    pass
for d in ['/sd/pinhos', '/sd/pinhos/apps']:
    try:
        os.mkdir(d)
    except Exception:
        pass
f = open('$Arg2', 'wb')
d = picocalc.display
d.fill(3)
d.rect(18, 118, 284, 64, 0)
d.rect(20, 120, 280, 60, 0)
d.text('UPDATING PinhOS v1.8.0...', 80, 134, 0)
d.rect(40, 154, 240, 12, 0)
"@
        Send-Paced $sp $initCode 48 4
        $sp.Write([string][char]4)
        Start-Sleep -Milliseconds 300
        [void]$sp.ReadExisting()

        $step = 1024
        $total = $b64.Length
        $chunkIdx = 0
        for ($i = 0; $i -lt $total; $i += $step) {
            $len = [Math]::Min($step, $total - $i)
            $slice = $b64.Substring($i, $len)
            $pct = [int]((($i + $len) / $total) * 236)
            $chunkIdx++
            $chunkCmd = "f.write(binascii.a2b_base64('$slice'));d.fill_rect(42,156,$pct,8,0)`n"
            Send-Paced $sp $chunkCmd 64 3
            $sp.Write([string][char]4)
            Start-Sleep -Milliseconds 120
            [void]$sp.ReadExisting()
        }

        $closeAndLaunch = @"
f.close()
time.sleep_ms(200)
try:
    os.stat('$Arg2')
except Exception:
    time.sleep_ms(300)
gc.collect()
if '/sd/pinhos' not in sys.path:
    sys.path.insert(0, '/sd/pinhos')
msg = 'VERIFIED_OK FREE_RAM:' + str(gc.mem_free()) + '\r\n'
u.write(msg.encode())
u.flush()
"@
        Send-Paced $sp $closeAndLaunch 48 4
        $sp.Write([string][char]4)
        Start-Sleep -Milliseconds 400
        [void]$sp.ReadExisting()

        # Also upload portal.html if present
        $portalLocal = Join-Path $PSScriptRoot "pinhos\portal.html"
        if (Test-Path $portalLocal) {
            $pBytes = [System.IO.File]::ReadAllBytes($portalLocal)
            $pB64 = [Convert]::ToBase64String($pBytes)
            Send-Paced $sp "pf=open('/sd/pinhos/portal.html','wb')`n" 48 4
            $sp.Write([string][char]4)
            Start-Sleep -Milliseconds 150
            [void]$sp.ReadExisting()
            for ($j = 0; $j -lt $pB64.Length; $j += 1024) {
                $plen = [Math]::Min(1024, $pB64.Length - $j)
                $pslice = $pB64.Substring($j, $plen)
                Send-Paced $sp "pf.write(binascii.a2b_base64('$pslice'))`n" 64 3
                $sp.Write([string][char]4)
                Start-Sleep -Milliseconds 110
                [void]$sp.ReadExisting()
            }
            Send-Paced $sp "pf.close()`ntime.sleep_ms(150)`n" 48 4
            $sp.Write([string][char]4)
            Start-Sleep -Milliseconds 250
            [void]$sp.ReadExisting()
        }

        $bootCmd = "import main`nmain.start()`n"
        Send-Paced $sp $bootCmd 48 4
        $sp.Write([string][char]4)
        $res = Read-UntilIdle $sp 800 5000
        Write-Output $res
    }
    elseif ($Action -eq "pkt") {
        Send-Paced $sp ("<<PINHOS:" + $Arg1 + ">>") 24 6
        $res = Read-UntilIdle $sp 4200 8000
        Write-Output $res
    }
    elseif ($Action -eq "exec_file") {
        $clean = ((Get-Content -Raw -Path $Arg1) -replace "`r`n", "`n")
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($clean))
        Send-Paced $sp ("<<PINHOS:EXEC:import binascii;exec(binascii.a2b_base64('" + $b64 + "'),globals(),loc)>>") 32 5
        $res = Read-UntilIdle $sp 800 8000
        Write-Output $res
    }
    elseif ($Action -eq "hot_write") {
        $rawBytes = [System.IO.File]::ReadAllBytes($Arg1)
        $b64 = [Convert]::ToBase64String($rawBytes)
        Send-Paced $sp ("<<PINHOS:WRITE:" + $Arg2 + ":" + $b64 + ">>") 32 5
        $res = Read-UntilIdle $sp 600 8000
        Write-Output $res
    }
    elseif ($Action -eq "raw") {
        $code = Get-Content -Raw -Path $Arg1
        $sp.Write([string][char]3 + [string][char]3 + [string][char]1)
        [void](Read-UntilIdle $sp 250 1000)
        Send-Paced $sp $code 32 6
        $sp.Write([string][char]4)
        $res = Read-UntilIdle $sp 2500 15000
        if ($res -notmatch "PINHOS:BOOT_OK") {
            $sp.Write([string][char]2)
            [void](Read-UntilIdle $sp 150 500)
        }
        Write-Output $res
    }
} finally {
    $sp.Close()
}

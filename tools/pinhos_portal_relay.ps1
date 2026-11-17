param(
    [string]$PortName = "COM4",
    [int]$BaudRate = 115200,
    [int]$HttpPort = 8080
)

$ErrorActionPreference = "Stop"
$htmlPath = Join-Path $PSScriptRoot "pinhos\portal.html"

$sp = New-Object System.IO.Ports.SerialPort $PortName, $BaudRate, 'None', 8, 'One'
$sp.ReadBufferSize = 65536
$sp.ReadTimeout = 400
$sp.WriteTimeout = 1000
$sp.Open()

function Send-BridgeCmd([string]$pkt, [int]$maxWaitMs = 900) {
    try {
        [void]$sp.ReadExisting()
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("<<PINHOS:" + $pkt + ">>")
        for ($i = 0; $i -lt $bytes.Length; $i += 32) {
            $len = [Math]::Min(32, $bytes.Length - $i)
            $sp.Write($bytes, $i, $len)
            Start-Sleep -Milliseconds 3
        }
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $sb = New-Object System.Text.StringBuilder
        while ($sw.ElapsedMilliseconds -lt $maxWaitMs) {
            if ($sp.BytesToRead -gt 0) {
                [void]$sb.Append($sp.ReadExisting())
                if ($sb.ToString().Contains(">>")) {
                    break
                }
            } else {
                Start-Sleep -Milliseconds 8
            }
        }
        return $sb.ToString()
    } catch {
        return ""
    }
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$HttpPort/")
$listener.Start()
Write-Output "PinhOS WebPortal Live at http://localhost:$HttpPort/"

$lastGoodState = '{"ver":"1.7.0","theme":"FLIPPER","menu":"MAIN","view":"","sel":0,"items":["DASHBOARD // SYSTEM TELEMETRY","PINHOS APP STORE & PLUGINS","TERMINAL // BUSYBOX SHELL","NETWORK & REMOTE WEBPORTAL","HARDWARE LAB & SYSTEM LOGS","GIT OTA & CONFIG SNAPSHOTS","SYSTEM & HARDWARE SETTINGS"],"desc":"Live RP2350 Telemetry","cpu":12,"mhz":150,"ram_free":265,"ram_pct":18,"bat":100,"temp":28,"ip":"192.168.1.93","rssi":-55,"lcd":80,"kb":60,"uptime":"1m 0s"}'

try {
    while ($listener.IsListening) {
        $ctx = $listener.GetContext()
        $req = $ctx.Request
        $res = $ctx.Response
        $path = $req.Url.AbsolutePath

        try {
            if ($path -eq "/favicon.ico") {
                $res.StatusCode = 204
            }
            elseif ($path -eq "/api/state" -or $path -eq "/api/status") {
                $raw = Send-BridgeCmd "STATE"
                if ($raw -match "<<PINHOS:STATE:(\{.*\})>>") {
                    $lastGoodState = $Matches[1]
                }
                $buf = [System.Text.Encoding]::UTF8.GetBytes($lastGoodState)
                $res.ContentType = "application/json"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
            elseif ($path.StartsWith("/api/key/")) {
                $k = $path.Substring(9)
                [void](Send-BridgeCmd ("KEY:" + $k.ToUpper()))
                $buf = [System.Text.Encoding]::UTF8.GetBytes('{"ok":true}')
                $res.ContentType = "application/json"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
            elseif ($path.StartsWith("/api/act/")) {
                $a = [System.Uri]::UnescapeDataString($path.Substring(9))
                [void](Send-BridgeCmd ("ACT:" + $a))
                $buf = [System.Text.Encoding]::UTF8.GetBytes('{"ok":true}')
                $res.ContentType = "application/json"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
            elseif ($path.StartsWith("/api/click_row/")) {
                $r = $path.Substring(15)
                [void](Send-BridgeCmd ("ROW:" + $r))
                $buf = [System.Text.Encoding]::UTF8.GetBytes('{"ok":true}')
                $res.ContentType = "application/json"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
            elseif ($path.StartsWith("/api/toast/")) {
                $m = [System.Uri]::UnescapeDataString($path.Substring(11))
                [void](Send-BridgeCmd ("TOAST:" + $m))
                $buf = [System.Text.Encoding]::UTF8.GetBytes('{"ok":true}')
                $res.ContentType = "application/json"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
            elseif ($path.StartsWith("/api/sh/")) {
                $shCmd = [System.Uri]::UnescapeDataString($path.Substring(8))
                $raw = Send-BridgeCmd ("SH:" + $shCmd) 15000
                $outTxt = ""
                if ($raw -match "(?s)<<PINHOS:SH_OUT:(.*?)>>") {
                    $outTxt = $Matches[1]
                }
                $buf = [System.Text.Encoding]::UTF8.GetBytes($outTxt)
                $res.ContentType = "text/plain; charset=utf-8"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
            else {
                $buf = [System.IO.File]::ReadAllBytes($htmlPath)
                $res.ContentType = "text/html; charset=utf-8"
                $res.ContentLength64 = $buf.Length
                $res.OutputStream.Write($buf, 0, $buf.Length)
            }
        } catch {
            $res.StatusCode = 500
        } finally {
            $res.Close()
        }
    }
} finally {
    $listener.Stop()
    if ($sp.IsOpen) {
        $sp.Close()
    }
}

# Runs the finished GAIA CascadeLens app on a Windows computer that has no Python.
# It does the same job as serve.py, using the PowerShell that every Windows already has.
#
# usage: powershell -ExecutionPolicy Bypass -File serve.ps1 [-Port 8765] [-NoBrowser]
#
# Everything is served from the app folder. The browser is told to refuse any request off this computer, so the app works with no internet.
# Range support is what makes the measurement inspector work: it reads single pixels out of large rasters.
param([int]$Port = 8765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $here 'app'
if (-not (Test-Path (Join-Path $app 'index.html'))) {
    # Started from the project folder, where the build is in frontend/dist
    $app = Join-Path (Join-Path (Split-Path -Parent $here) 'frontend') 'dist'
}
if (-not (Test-Path (Join-Path $app 'index.html'))) {
    Write-Host "Cannot find the app at $app. Keep serve.ps1 next to the app folder."
    exit 1
}
$app = (Resolve-Path $app).Path

$csp = "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'sha256-CIN9TmB8AQkNCIf/cEAUqgdyYnFycAPMnEdhSTvaAJ8=' 'wasm-unsafe-eval'"
$types = @{
    '.html' = 'text/html'; '.js' = 'text/javascript'; '.mjs' = 'text/javascript'; '.css' = 'text/css'
    '.json' = 'application/json'; '.geojson' = 'application/json'; '.tif' = 'image/tiff'; '.png' = 'image/png'
    '.jpg' = 'image/jpeg'; '.jpeg' = 'image/jpeg'; '.svg' = 'image/svg+xml'; '.ico' = 'image/x-icon'; '.webp' = 'image/webp'
    '.wasm' = 'application/wasm'; '.txt' = 'text/plain'; '.csv' = 'text/csv'; '.woff' = 'font/woff'; '.woff2' = 'font/woff2'
    '.pbf' = 'application/x-protobuf'; '.webmanifest' = 'application/manifest+json'
}

# A "localhost" address needs no administrator rights, and cannot be reached from another computer
$listener = $null
$used = 0
for ($p = $Port; $p -lt $Port + 20; $p++) {
    $l = New-Object System.Net.HttpListener
    $l.Prefixes.Add("http://localhost:$p/")
    try {
        $l.Start()
        $listener = $l
        $used = $p
        break
    } catch {
        try { $l.Close() } catch { }
    }
}
if ($null -eq $listener) {
    Write-Host 'No free port found.'
    exit 1
}

# One of these runs on each of several threads, because a map asks for many tiles at once
$worker = {
    param($listener, $root, $csp, $types)
    $sep = [IO.Path]::DirectorySeparatorChar
    $prefix = $root.TrimEnd($sep) + $sep
    $buffer = New-Object byte[] 65536
    while ($listener.IsListening) {
        try { $ctx = $listener.GetContext() } catch { break }
        $req = $ctx.Request
        $res = $ctx.Response
        try {
            $url = $req.Url.AbsolutePath
            $cache = 'no-cache'  # The page and manifests: a new version shows on a normal reload
            if ($url.StartsWith('/assets/')) { $cache = 'public, max-age=31536000, immutable' }  # Their names change whenever their content does
            elseif ($url.StartsWith('/data/') -and -not $url.EndsWith('.json')) { $cache = 'public, max-age=86400' }
            $res.AddHeader('Content-Security-Policy', $csp)
            $res.AddHeader('Accept-Ranges', 'bytes')
            $res.AddHeader('Cache-Control', $cache)

            $full = $null
            if ($req.HttpMethod -eq 'GET' -or $req.HttpMethod -eq 'HEAD') {
                try {
                    $rel = [Uri]::UnescapeDataString($url).TrimStart('/')
                    if ($rel -eq '' -or $rel.EndsWith('/')) { $rel += 'index.html' }
                    $candidate = [IO.Path]::GetFullPath([IO.Path]::Combine($root, $rel))
                    # Nothing outside the app folder is ever served
                    if ($candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -and [IO.File]::Exists($candidate)) { $full = $candidate }
                } catch { }
            } else {
                $res.StatusCode = 405
                $res.ContentLength64 = 0
                continue
            }
            if ($null -eq $full) {
                $res.StatusCode = 404
                $res.ContentLength64 = 0
                continue
            }

            $file = [IO.File]::Open($full, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            try {
                $size = $file.Length
                $start = [long]0
                $length = $size
                $m = [regex]::Match([string]$req.Headers['Range'], '^bytes=(\d+)-(\d*)$')
                if ($m.Success) {
                    $start = [long]$m.Groups[1].Value
                    $end = $size - 1
                    if ($m.Groups[2].Value -ne '') { $end = [Math]::Min([long]$m.Groups[2].Value, $size - 1) }
                    if ($start -ge $size -or $end -lt $start) {
                        $res.StatusCode = 416
                        $res.AddHeader('Content-Range', "bytes */$size")
                        $res.ContentLength64 = 0
                        continue
                    }
                    $length = $end - $start + 1
                    $res.StatusCode = 206
                    $res.AddHeader('Content-Range', "bytes $start-$end/$size")
                }
                $type = $types[[IO.Path]::GetExtension($full).ToLowerInvariant()]
                if (-not $type) { $type = 'application/octet-stream' }
                $res.ContentType = $type
                $res.ContentLength64 = $length
                if ($req.HttpMethod -eq 'GET') {
                    [void]$file.Seek($start, [IO.SeekOrigin]::Begin)
                    $left = $length
                    while ($left -gt 0) {
                        $n = $file.Read($buffer, 0, [int][Math]::Min([long]$buffer.Length, $left))
                        if ($n -le 0) { break }
                        $res.OutputStream.Write($buffer, 0, $n)
                        $left -= $n
                    }
                }
            } finally {
                $file.Dispose()
            }
        } catch {
            # Browsers drop connections when a tile is no longer needed. That is normal, not a fault
        } finally {
            try { $res.Close() } catch { }
        }
    }
}

$threads = 8
$pool = [runspacefactory]::CreateRunspacePool(1, $threads)
$pool.Open()
for ($i = 0; $i -lt $threads; $i++) {
    $ps = [powershell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($worker).AddArgument($listener).AddArgument($app).AddArgument($csp).AddArgument($types)
    [void]$ps.BeginInvoke()
}

$address = "http://localhost:$used/"
Write-Host "GAIA CascadeLens is running.`n`n    $address`n`nIt should open in your default browser. To use Brave or another browser, paste that address into it."
Write-Host 'Do not open index.html directly: browsers block that.'
Write-Host 'Keep this window open while you use the app. Close it, or press Ctrl+C, to stop.'
if (-not $NoBrowser) {
    try { Start-Process $address } catch { }
}
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    $listener.Stop()
}

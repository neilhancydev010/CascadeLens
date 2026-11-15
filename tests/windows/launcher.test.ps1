# Checks that the Windows launcher starts the app on a computer with no Python, using only what Windows has.
# Run with Windows PowerShell from the project folder:  powershell -ExecutionPolicy Bypass -File tests\windows\launcher.test.ps1
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

# A folder name with a space and brackets, as a second download of the zip gets
$dir = Join-Path ([IO.Path]::GetTempPath()) 'CascadeLens (1)'
if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
New-Item -ItemType Directory -Force (Join-Path $dir 'app\assets'), (Join-Path $dir 'app\data') | Out-Null
Copy-Item (Join-Path $repo 'product\Start CascadeLens.bat'), (Join-Path $repo 'product\serve.ps1'), (Join-Path $repo 'product\serve.py') $dir
Set-Content (Join-Path $dir 'app\index.html') '<!doctype html><title>test</title>'
Set-Content (Join-Path $dir 'app\assets\a.js') 'export {}'
Set-Content (Join-Path $dir 'app\data\m.json') '{}'
$raster = New-Object byte[] 1024
for ($i = 0; $i -lt 1024; $i++) { $raster[$i] = $i % 251 }
[IO.File]::WriteAllBytes((Join-Path $dir 'app\data\r.tif'), $raster)

# Only Windows' own folders stay on the path, so no Python can be found
$oldPath = $env:PATH
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
foreach ($name in 'python', 'py') {
    cmd /c "where $name >nul 2>nul"
    if ($LASTEXITCODE -eq 0) { throw "$name is still on the path, so this would not test the PowerShell server" }
}
$launcher = Start-Process cmd.exe -ArgumentList '/c', '"Start CascadeLens.bat"' -WorkingDirectory $dir -PassThru -WindowStyle Hidden
$env:PATH = $oldPath

$failed = 0
function Check($what, $ok) {
    if ($ok) { Write-Host "ok    $what" } else { Write-Host "FAIL  $what"; $script:failed++ }
}
function Fetch($path, $range) {
    $head = Join-Path $dir 'head.txt'
    $body = Join-Path $dir 'body.bin'
    Remove-Item $head, $body -ErrorAction SilentlyContinue
    $extra = @()
    if ($range) { $extra = @('-H', "Range: bytes=$range") }
    & curl.exe -s --path-as-is -D $head -o $body @extra "http://localhost:8765$path" | Out-Null
    $text = ''
    if (Test-Path $head) { $text = [IO.File]::ReadAllText($head) }
    $bytes = New-Object byte[] 0
    if (Test-Path $body) { $bytes = [IO.File]::ReadAllBytes($body) }
    $status = 0
    if ($text -match '^HTTP/\S+ (\d+)') { $status = [int]$Matches[1] }
    return @{ status = $status; head = $text; body = $bytes }
}

try {
    $up = $false
    for ($i = 0; $i -lt 60 -and -not $up; $i++) {
        Start-Sleep -Milliseconds 500
        $up = (Fetch '/' $null).status -eq 200
    }
    Check 'the launcher starts the app with no Python' $up

    $r = Fetch '/' $null
    Check 'the page is HTML' ($r.head -match '(?im)^Content-Type: text/html')
    Check 'the page forbids requests off this computer' ($r.head -match "(?im)^Content-Security-Policy: default-src 'self'")
    Check 'the page is checked again on reload' ($r.head -match '(?im)^Cache-Control: no-cache')

    $r = Fetch '/assets/a.js' $null
    Check 'scripts have the type browsers require' ($r.status -eq 200 -and $r.head -match '(?im)^Content-Type: text/javascript')
    Check 'built assets are cached for good' ($r.head -match '(?im)^Cache-Control: .*immutable')

    $r = Fetch '/data/r.tif' $null
    Check 'a whole raster arrives' ($r.status -eq 200 -and $r.body.Length -eq 1024)
    Check 'rasters are cached for a day' ($r.head -match '(?im)^Cache-Control: public, max-age=86400')

    $r = Fetch '/data/r.tif' '10-19'
    Check 'a byte range answers 206' ($r.status -eq 206 -and $r.head -match '(?im)^Content-Range: bytes 10-19/1024')
    Check 'a byte range holds exactly those bytes' ($r.body.Length -eq 10 -and $r.body[0] -eq 10 -and $r.body[9] -eq 19)

    $r = Fetch '/data/r.tif' '1000-'
    Check 'an open range runs to the end' ($r.status -eq 206 -and $r.body.Length -eq 24 -and $r.body[23] -eq (1023 % 251))

    $r = Fetch '/data/r.tif' '5000-'
    Check 'a range past the end answers 416' ($r.status -eq 416)

    Check 'a missing file answers 404' ((Fetch '/nope.js' $null).status -eq 404)
    Check 'the manifest is checked again on reload' ((Fetch '/data/m.json' $null).head -match '(?im)^Cache-Control: no-cache')
    $r = Fetch '/..%2fserve.ps1' $null
    Check 'nothing outside the app folder is served' ($r.status -ne 200 -and $r.status -ne 206)
    $r = Fetch '/../serve.ps1' $null
    Check 'a parent-folder path is refused' ($r.status -ne 200 -and $r.status -ne 206)
} finally {
    cmd /c "taskkill /T /F /PID $($launcher.Id) >nul 2>nul"
}
if ($failed) { Write-Host "$failed check(s) failed"; exit 1 }
Write-Host 'All launcher checks passed.'

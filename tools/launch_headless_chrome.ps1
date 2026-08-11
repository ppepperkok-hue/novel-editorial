param(
    [string]$ChromePath = "",
    [string]$ProfileDir = "",
    [switch]$DryRun
)

# Resolve Chrome executable: explicit arg > env > PATH > common install locations.
function Resolve-ChromePath {
    param([string]$Explicit)
    if ($Explicit -and (Test-Path -LiteralPath $Explicit)) { return $Explicit }
    $envChrome = $env:CHROME_EXE
    if ($envChrome -and (Test-Path -LiteralPath $envChrome)) { return $envChrome }
    $cmd = Get-Command chrome.exe, chrome -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return ""
}

$chrome = Resolve-ChromePath -Explicit $ChromePath
if (-not $chrome) {
    Write-Error "Chrome not found. Set CHROME_EXE or pass -ChromePath."
    exit 1
}

if ($ProfileDir) {
    $profile = $ProfileDir
} elseif ($env:CHROME_PROFILE_DIR) {
    $profile = $env:CHROME_PROFILE_DIR
} else {
    $profile = Join-Path $PSScriptRoot 'chrome-profile'
}

$chromeArgs = @(
    '--headless=new',
    '--remote-debugging-port=9333',
    "--user-data-dir=$profile",
    '--no-first-run',
    '--disable-gpu',
    'about:blank'
)

if ($DryRun) {
    Write-Output ("chrome=" + $chrome)
    Write-Output ("profile=" + $profile)
    Write-Output ("args=" + ($chromeArgs -join ' '))
    exit 0
}

$p = Start-Process -FilePath $chrome -ArgumentList $chromeArgs -WindowStyle Hidden -PassThru
Write-Output ("chrome pid=" + $p.Id)
Start-Sleep -Seconds 3
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9333/json/version' -UseBasicParsing -TimeoutSec 5
    Write-Output $r.Content
} catch {
    Write-Output ("cdp err: " + $_.Exception.Message)
}

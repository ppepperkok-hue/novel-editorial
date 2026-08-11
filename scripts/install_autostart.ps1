<#
Unified startup registration for the pipeline services.

Registers the pipeline API in the user Startup folder (n8n retired):
  - NovelEditorial-api.vbs   -> pythonw web_api on 127.0.0.1:8000

The Electron panel has its own auto-launch switch (Settings page), so it is
not registered here. Old launchers (NovelEditorial-n8n.vbs, n8n-start.vbs,
novel-editorial-8000.vbs, novel-editorial-8001.vbs) are removed on enable.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1          # enable
  powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1 -Disable # remove
#>

param(
    [switch]$Disable,
    [switch]$DryRun,
    [string]$PipelineRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $PipelineRoot) {
    $PipelineRoot = Split-Path -Parent $PSScriptRoot
}
$PipelineRoot = (Resolve-Path -LiteralPath $PipelineRoot).Path
$StartupDir = [Environment]::GetFolderPath("Startup")

$ManagedNames = @(
    "NovelEditorial-api.vbs"
)
$LegacyNames = @(
    "NovelEditorial-n8n.vbs",
    "n8n-start.vbs",
    "novel-editorial-8000.vbs",
    "novel-editorial-8001.vbs"
)

function Resolve-Pythonw {
    $exe = $env:PYTHON_EXE
    if (-not $exe) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $exe = $cmd.Source }
    }
    if (-not $exe) { throw "python not found; set PYTHON_EXE" }
    $pyw = Join-Path (Split-Path -Parent $exe) "pythonw.exe"
    if (-not (Test-Path -LiteralPath $pyw)) {
        throw "pythonw.exe not found next to $exe"
    }
    return $pyw
}

function New-ApiVbs {
    $pythonw = Resolve-Pythonw
    return @"
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "$PipelineRoot"
ws.Run """$pythonw"" -m novel_editorial.web_api --db demo.db --port 8000", 0, False
"@
}

function Remove-Items {
    param([string[]]$Names)
    foreach ($n in $Names) {
        $p = Join-Path $StartupDir $n
        if (Test-Path -LiteralPath $p) {
            if ($DryRun) {
                Write-Output "would remove: $p"
            } else {
                Remove-Item -LiteralPath $p -Force
                Write-Output "removed: $p"
            }
        }
    }
}

if ($Disable) {
    Remove-Items -Names ($ManagedNames + $LegacyNames)
    Write-Output "autostart disabled"
    exit 0
}

$targets = @{
    (Join-Path $StartupDir "NovelEditorial-api.vbs") = (New-ApiVbs)
}

if ($DryRun) {
    Write-Output "PipelineRoot: $PipelineRoot"
    Write-Output "StartupDir  : $StartupDir"
    Write-Output "Would remove legacy:"
    Remove-Items -Names $LegacyNames
    Write-Output "Would write:"
    foreach ($k in $targets.Keys) {
        Write-Output "  $k"
    }
    exit 0
}

Remove-Items -Names $LegacyNames
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
foreach ($k in $targets.Keys) {
    [System.IO.File]::WriteAllText($k, $targets[$k], $utf8Bom)
    Write-Output "registered: $k"
}
Write-Output "autostart enabled (web_api:8000)"

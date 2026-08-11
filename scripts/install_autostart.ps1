<#
Unified startup registration for the pipeline services.

Registers two launch items in the user Startup folder:
  - NovelPipeline-n8n.vbs   -> scripts/start_n8n.ps1 (loads project env, hidden)
  - NovelPipeline-api.vbs   -> pythonw web_api on 127.0.0.1:8000

The Electron panel has its own auto-launch switch (Settings page), so it is
not registered here. Old ad-hoc launchers (n8n-start.vbs,
novel-pipeline-8000.vbs, novel-pipeline-8001.vbs) are removed on enable.

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
    "NovelPipeline-n8n.vbs",
    "NovelPipeline-api.vbs"
)
$LegacyNames = @(
    "n8n-start.vbs",
    "novel-pipeline-8000.vbs",
    "novel-pipeline-8001.vbs"
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

function New-N8nVbs {
    $ps1 = Join-Path $PipelineRoot "scripts\start_n8n.ps1"
    return @"
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "$PipelineRoot"
ws.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$ps1""", 0, False
"@
}

function New-ApiVbs {
    $pythonw = Resolve-Pythonw
    return @"
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "$PipelineRoot"
ws.Run """$pythonw"" -m novel_pipeline.web_api --db demo.db --port 8000", 0, False
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
    (Join-Path $StartupDir "NovelPipeline-n8n.vbs") = (New-N8nVbs)
    (Join-Path $StartupDir "NovelPipeline-api.vbs") = (New-ApiVbs)
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
foreach ($k in $targets.Keys) {
    Set-Content -LiteralPath $k -Value $targets[$k] -Encoding ASCII
    Write-Output "registered: $k"
}
Write-Output "autostart enabled (n8n + web_api:8000)"

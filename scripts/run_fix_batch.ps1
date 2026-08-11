<#
Dispatch fix task packs to independent Codex CLI agents in parallel.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/run_fix_batch.ps1 `
    -TaskFiles docs/planning/round3-fix-tasks/R3-A1-services.md,docs/planning/round3-fix-tasks/R3-A2-core.md `
    -Model deepseek-v4-flash -Wait
  powershell -ExecutionPolicy Bypass -File scripts/run_fix_batch.ps1 -TaskFiles ... -DryRun

Each task pack is a self-contained markdown (bug list, allowed files, acceptance).
Workers write logs to docs/tmp_fix/<name>.log and .err.
#>
param(
    [string[]]$TaskFiles = @(),
    [string]$Model = "",
    [switch]$DryRun,
    [switch]$Wait
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($TaskFiles.Count -eq 0) {
    throw "TaskFiles is required"
}
if ($TaskFiles.Count -eq 1 -and $TaskFiles[0] -match ",") {
    $TaskFiles = $TaskFiles[0] -split ","
}
$tmpDir = Join-Path $root "docs/tmp_fix"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$worker = Join-Path $root "scripts\_run_fix_worker.ps1"

$procs = @()
foreach ($tf in $TaskFiles) {
    $task = [System.IO.Path]::GetFullPath((Join-Path $root $tf))
    if (-not (Test-Path -LiteralPath $task)) {
        throw "task file not found: $task"
    }
    $name = [System.IO.Path]::GetFileNameWithoutExtension($tf)
    $outLog = Join-Path $tmpDir ($name + ".log")
    $errLog = Join-Path $tmpDir ($name + ".err")

    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$worker`"",
        "-Task", "`"$task`"",
        "-Out", "`"$outLog`"",
        "-Err", "`"$errLog`""
    )
    if ($Model) {
        $argList += @("-Model", "`"$Model`"")
    }
    if ($DryRun) {
        Write-Host "[DryRun] $name -> $outLog"
        Write-Host "  node <codex.js> exec --ephemeral - < $task"
        continue
    }
    Write-Host "Starting fix agent: $name"
    $p = Start-Process -FilePath "powershell" -ArgumentList $argList `
        -WindowStyle Hidden -PassThru
    $procs += @{ Name = $name; Process = $p; Out = $outLog; Err = $errLog }
}

if ($DryRun) {
    exit 0
}
if ($Wait) {
    foreach ($item in $procs) {
        try {
            Wait-Process -Id $item.Process.Id -ErrorAction Stop
        }
        catch {
            # Process already exited between Start-Process and Wait-Process.
        }
        $ok = Test-Path -LiteralPath $item.Out
        $size = if ($ok) { (Get-Item $item.Out).Length } else { 0 }
        $errSize = if (Test-Path -LiteralPath $item.Err) { (Get-Item $item.Err).Length } else { 0 }
        Write-Host ("Finished fix agent: " + $item.Name + " out=" + $size + " err=" + $errSize)
    }
}
else {
    Write-Host ("Dispatched " + $procs.Count + " fix agents. Logs in " + $tmpDir)
}

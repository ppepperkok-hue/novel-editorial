<#
One-shot rename executed at next logon, before Codex/explorer hold the
directory. Registered as scheduled task NovelEditorialRenameOnce and it
deletes itself when done (or when there is nothing to do).

All output is ASCII: Windows PowerShell 5.1 misreads UTF-8 without BOM.
#>

$ErrorActionPreference = "Stop"
$old = "E:\code\novel-pipeline"
$new = "E:\code\novel-editorial"
$task = "NovelEditorialRenameOnce"

function Remove-Task {
    schtasks /Delete /TN $task /F 2>$null | Out-Null
}

if (-not (Test-Path $old) -or (Test-Path $new)) {
    Remove-Task
    exit 0
}

# Stop leftover services whose command line points at the old directory.
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "novel-pipeline" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Seconds 2

Rename-Item -LiteralPath $old -NewName "novel-editorial"
Write-Host "Directory renamed to $new"

$startup = [Environment]::GetFolderPath("Startup")
foreach ($legacy in @("NovelPipeline-api.vbs", "NovelPipeline-api.vbs.disabled")) {
    $p = Join-Path $startup $legacy
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Force
        Write-Host "Removed legacy startup entry: $p"
    }
}

Set-Location $new
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1
Remove-Task
Write-Host "Done: renamed and startup entry registered."

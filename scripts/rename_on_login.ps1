<#
One-shot rename executed at next logon via HKCU RunOnce (no admin needed).
It stops leftover services pointing at the old directory, renames it,
rebuilds the startup entry and removes itself. On failure it re-arms the
RunOnce key so the next logon tries again.

All output is ASCII: Windows PowerShell 5.1 misreads UTF-8 without BOM.
#>

$ErrorActionPreference = "Continue"
$old = "E:\code\novel-pipeline"
$new = "E:\code\novel-editorial"
$runOnceKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
$runOnceName = "NovelEditorialRenameOnce"

function Disarm {
    Remove-ItemProperty -Path $runOnceKey -Name $runOnceName -ErrorAction SilentlyContinue
}

function Rearm {
    Set-ItemProperty -Path $runOnceKey -Name $runOnceName -Value 'powershell -NoProfile -ExecutionPolicy Bypass -File "E:\code\novel-pipeline\scripts\rename_on_login.ps1"'
}

if (-not (Test-Path $old) -or (Test-Path $new)) {
    Disarm
    exit 0
}

try {
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match "novel[-_]pipeline" } |
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
    Disarm
    Write-Host "Done: renamed and startup entry registered."
}
catch {
    Rearm
    Write-Host ("Rename failed, will retry on next logon: " + $_.Exception.Message)
    exit 1
}

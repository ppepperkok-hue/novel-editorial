<#
Finish the project directory rename:
  novel-pipeline  ->  novel-editorial
and rebuild the silent startup entry.

NOTE: this script must NOT run while Codex is open (Codex holds a handle on
the old directory). Fully quit Codex first, then run:
  powershell -ExecutionPolicy Bypass -File scripts/finish_rename.ps1

All output is ASCII on purpose: Windows PowerShell 5.1 misreads UTF-8
without BOM and non-ASCII strings can break the parser.
#>

$ErrorActionPreference = "Stop"
Set-Location E:\code

$old = "E:\code\novel-pipeline"
$new = "E:\code\novel-editorial"

if (Test-Path $new) {
    Write-Host "Target directory already exists: $new . Aborting to avoid overwrite."
    exit 1
}
if (-not (Test-Path $old)) {
    Write-Host "Old directory not found: $old . It may already be renamed."
    exit 0
}

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
Write-Host "Done: directory renamed and new startup entry registered (NovelEditorial-api.vbs)."

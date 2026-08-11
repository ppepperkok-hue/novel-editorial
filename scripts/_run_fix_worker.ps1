<#
Internal worker for run_fix_batch.ps1: runs one codex exec fix task.
Reads the task prompt from a markdown file and pipes it to `codex exec --ephemeral -`.
#>
param(
    [string]$Task = "",
    [string]$Out = "",
    [string]$Err = "",
    [string]$Model = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

if (-not $Task -or -not (Test-Path -LiteralPath $Task)) {
    throw "task file not found: $Task"
}
$codexCmd = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codexCmd) {
    throw "codex CLI not found on PATH"
}
$npmBin = Split-Path -Parent $codexCmd.Source
$codexJs = Join-Path $npmBin "node_modules\@openai\codex\bin\codex.js"
if (-not (Test-Path -LiteralPath $codexJs)) {
    throw "codex.js not found: $codexJs"
}

# Same invocation style as run_review.ps1: the prompt goes in as a
# command-line argument (single line), node is launched via Start-Process
# hidden, and stdout/stderr are redirected to files. No console window.
$taskText = Get-Content -LiteralPath $Task -Raw -Encoding UTF8
$taskText = $taskText -replace "`r?`n", " "
if ($taskText.Length -gt 15000) {
    throw "task text is $($taskText.Length) chars (> 15000); split the task file into smaller tasks"
}
$parts = @(
    '"' + $codexJs + '"',
    "exec",
    "--ephemeral"
)
if ($Model) {
    $parts += "-m"
    $parts += '"' + $Model + '"'
}
$parts += '"' + $taskText + '"'
$cmdLine = $parts -join " "
$p = Start-Process -FilePath "node" -ArgumentList $cmdLine `
    -WorkingDirectory $root -RedirectStandardOutput $Out `
    -RedirectStandardError $Err -WindowStyle Hidden -Wait -PassThru
exit $p.ExitCode

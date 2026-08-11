<#
Run an independent reviewer via Codex CLI and save the report.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope full
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope commit -Commit HEAD~3
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope uncommitted -Model gpt-5-mini

The reviewer runs as a separate agent with a strict engineering persona and
produces a P0-P3 report under docs/reviews/.
#>

param(
    [ValidateSet("full", "uncommitted", "commit")]
    [string]$Scope = "uncommitted",
    [string]$Commit = "",
    [string]$Model = "",
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Out) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmm"
    $Out = Join-Path $root ("docs/reviews/" + $stamp + "-" + $Scope + "-review.md")
}
$Out = [System.IO.Path]::GetFullPath($Out)
New-Item -ItemType Directory -Path (Split-Path -Parent $Out) -Force | Out-Null

$persona = @"
You are an extremely strict, highly skilled senior engineer performing an independent code review.
Review the requested scope carefully and report ONLY findings backed by evidence.

Requirements:
1. Run the project verification baseline first when applicable (python run_tests.py / npm test / npm run build).
2. Scan for real issues: silent failures, fake green, hardcoded paths/secrets, lock/concurrency bugs,
   SQL placeholder mistakes, encoding problems, dead code, missing tests, scope violations.
3. Classify every finding as P0 (must fix now), P1 (high risk), P2 (low risk), P3 (docs/UX).
4. Every finding must carry evidence: file:line, command output, or reproduction steps. No feelings.
5. Produce a report with: scope, baseline results, P0-P3 findings, impact table, and an honest conclusion.
6. Do NOT fix anything. This is a review-only pass.
"@

$args = @("exec", "review")
if ($Scope -eq "uncommitted") {
    $args += "--uncommitted"
    # NOTE: --uncommitted and [PROMPT] are mutually exclusive; the built-in
    # review instructions already enforce strict evidence-backed findings.
}
elseif ($Scope -eq "commit") {
    if (-not $Commit) {
        Write-Host "Scope=commit requires -Commit <sha>"
        exit 1
    }
    $args += @("--commit", $Commit)
}
if ($Model) {
    $args += @("-m", $Model)
}
$args += "--ephemeral"
if ($Scope -ne "uncommitted") {
    $args += $persona
}

Write-Host "Reviewer: codex exec review ($Scope) -> $Out"
Write-Host "Note: a full review can take several minutes; do not close the terminal early."
codex @args 2>&1 | Tee-Object -FilePath $Out
Write-Host "Report written to: $Out"

<#
Run an independent reviewer via Codex CLI and save the report.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope full
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope slices
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope commit -Commit HEAD~3
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope uncommitted -Model gpt-5-mini
  powershell -ExecutionPolicy Bypass -File scripts/run_review.ps1 -Scope slices -DryRun

The reviewer runs as a separate agent with a strict engineering persona and
produces a P0-P3 report under docs/reviews/.

Workflow: run an incremental review (-Scope uncommitted) between development
steps, and a parallel slice review (-Scope slices) after the work is done.
#>

param(
    [ValidateSet("full", "uncommitted", "commit", "slices")]
    [string]$Scope = "uncommitted",
    [string]$Commit = "",
    [string]$Model = "",
    [string]$Out = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Call codex.js directly via node: the npm PowerShell shim mangles
# arguments/stdin for the review subcommand.
$codexCmd = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codexCmd) {
    Write-Host "codex CLI not found on PATH"
    exit 1
}
$npmBin = Split-Path -Parent $codexCmd.Source
$codexJs = Join-Path $npmBin "node_modules\@openai\codex\bin\codex.js"
if (-not (Test-Path $codexJs)) {
    Write-Host "codex.js not found: $codexJs"
    exit 1
}

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

function Get-ReviewArgs {
    param([string]$Focus = "")
    $a = @("exec", "review")
    if ($Scope -eq "uncommitted") {
        $a += "--uncommitted"
        # NOTE: --uncommitted and [PROMPT] are mutually exclusive; the built-in
        # review instructions already enforce strict evidence-backed findings.
    }
    elseif ($Scope -eq "commit") {
        if (-not $Commit) {
            throw "Scope=commit requires -Commit <sha>"
        }
        $a += @("--commit", $Commit)
    }
    if ($Model) {
        $a += @("-m", $Model)
    }
    $a += "--ephemeral"
    if ($Scope -ne "uncommitted") {
        $p = ($persona -replace "`r?`n", " ")
        if ($Focus) {
            $p += " Focus this review on the directory: $Focus"
        }
        $a += $p
    }
    return $a
}

if ($Scope -eq "slices") {
    $slicePaths = @{
        "core"    = "novel_editorial"
        "tools"   = "tools"
        "webapp"  = "webapp/src"
        "tests"   = "tests"
        "scripts" = "scripts"
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmm"
    $index = Join-Path $root ("docs/reviews/" + $stamp + "-slices-index.md")
    $procs = @()
    foreach ($name in $slicePaths.Keys) {
        $focus = $slicePaths[$name]
        $outFile = Join-Path $root ("docs/reviews/" + $stamp + "-slice-" + $name + ".md")
        $errFile = $outFile + ".err"
        $a = Get-ReviewArgs -Focus $focus
        $quoted = $a | ForEach-Object { '"' + $_ + '"' }
        $cmdLine = "node `"$codexJs`" " + ($quoted -join " ")
        if ($DryRun) {
            Write-Host "[DryRun] $name -> $outFile"
            Write-Host "  $cmdLine"
            continue
        }
        Write-Host "Starting slice review: $name (parallel)"
        $p = Start-Process -FilePath "node" -ArgumentList $quoted -WorkingDirectory $root `
            -RedirectStandardOutput $outFile -RedirectStandardError $errFile `
            -WindowStyle Hidden -PassThru
        $procs += @{ Name = $name; Process = $p; Out = $outFile; Err = $errFile }
    }
    if ($DryRun) {
        exit 0
    }
    foreach ($item in $procs) {
        Wait-Process -Id $item.Process.Id
        Write-Host ("Finished slice: " + $item.Name + " (exit " + $item.Process.ExitCode + ")")
    }
    $lines = @("# 并行分片审查索引", "", "生成时间：$stamp", "", "| 分片 | 报告 | 状态 |", "| --- | --- | --- |")
    foreach ($item in $procs) {
        $ok = Test-Path -LiteralPath $item.Out
        $size = if ($ok) { (Get-Item $item.Out).Length } else { 0 }
        $lines += ("| " + $item.Name + " | " + $item.Out + " | " + $size + " bytes |")
    }
    Set-Content -LiteralPath $index -Value $lines -Encoding UTF8
    Write-Host "Slice review done. Index: $index"
    exit 0
}

$a = Get-ReviewArgs
$quoted = $a | ForEach-Object { '"' + $_ + '"' }
$cmdLine = "node `"$codexJs`" " + ($quoted -join " ")
if ($DryRun) {
    Write-Host "[DryRun] $cmdLine -> $Out"
    exit 0
}
Write-Host "Reviewer: codex exec review ($Scope) -> $Out"
Write-Host "Note: a full review can take several minutes; do not close the terminal early."
& node $codexJs @a *> $Out
Write-Host "Report written to: $Out"

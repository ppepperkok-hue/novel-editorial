<#
注册 Windows 计划任务，每天定时运行 Python 日更调度器（de-n8n）。

用法（-DryRun 只打印命令，不注册）：
  powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 `
    -Time "08:00" -DbPath "demo.db" -DryRun

真实注册：
  powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 `
    -Time "08:00" -DbPath "demo.db"

删除任务：
  powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 -Remove
#>
param(
    [string]$Time = "08:00",
    [string]$TaskName = "NovelPipelineDaily",
    [string]$DbPath = "demo.db",
    [switch]$DryRun,
    [switch]$Remove
)

$projectDir = Split-Path -Parent $PSScriptRoot
$python = $env:PYTHON_EXE
if (-not $python) {
    $python = (Get-Command python).Source
}
$dbPath = Join-Path $projectDir $DbPath
$argList = "tools/editorial_daily.py --db `"$dbPath`" --trigger scheduled"
$command = "$python $argList"

if ($Remove) {
    if ($DryRun) {
        Write-Host "would remove task: $TaskName"
        exit 0
    }
    schtasks /Delete /TN $TaskName /F | Out-Null
    Write-Host "已删除计划任务 $TaskName。"
    exit 0
}

Write-Host "计划任务命令：$command"
Write-Host "工作目录：$projectDir"

if ($DryRun) {
    Write-Host "[DryRun] 未注册任务。"
    exit 0
}

$action = New-ScheduledTaskAction -Execute $python -Argument $argList -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Description "novel-pipeline 日更调度器（每天 $Time）" -Force
Write-Host "已注册计划任务 $TaskName，每天 $Time 运行。"

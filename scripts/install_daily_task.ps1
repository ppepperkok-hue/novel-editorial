<#
注册 Windows 计划任务，每天定时运行 novel-pipeline 自动日更。

用法（-DryRun 只打印命令，不注册）：
  powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 `
    -Premise "林舟重生回到高考前三个月。" -Chapters 3 -Daily 2 -DryRun

真实注册：
  powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 `
    -Premise "林舟重生回到高考前三个月。" -Chapters 3 -Daily 2 -Time "08:00"

删除任务：
  schtasks /Delete /TN NovelPipelineDaily /F
#>
param(
    [Parameter(Mandatory = $true)][string]$Premise,
    [int]$Chapters = 3,
    [int]$Daily = 2,
    [int]$MinChars = 2000,
    [int]$MaxChars = 2200,
    [string]$Time = "08:00",
    [string]$TaskName = "NovelPipelineDaily",
    [string]$DbPath = "demo.db",
    [switch]$DryRun
)

$projectDir = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
$dbPath = Join-Path $projectDir $DbPath
$argList = "-m novel_pipeline.autopilot --premise `"$Premise`" --chapters $Chapters --daily $Daily --min-chars $MinChars --max-chars $MaxChars --db `"$dbPath`""
$command = "$python $argList"

Write-Host "计划任务命令：$command"
Write-Host "工作目录：$projectDir"

if ($DryRun) {
    Write-Host "[DryRun] 未注册任务。"
    exit 0
}

$action = New-ScheduledTaskAction -Execute $python -Argument $argList -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Description "novel-pipeline 自动日更（每天 $Time）" -Force
Write-Host "已注册计划任务 $TaskName，每天 $Time 运行。"

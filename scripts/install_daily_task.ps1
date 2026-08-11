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
    [string]$TaskName = "NovelEditorialDaily",
    [string]$DbPath = "demo.db",
    [switch]$DryRun,
    [switch]$Remove
)

$projectDir = Split-Path -Parent $PSScriptRoot

function Resolve-PythonExe {
    # 1) Explicit overrides, same keys the desktop shell honors.
    foreach ($envKey in @("PYTHONW_EXE", "PYTHON_EXE")) {
        $candidate = [Environment]::GetEnvironmentVariable($envKey)
        if (-not $candidate) { continue }
        if (-not [System.IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $projectDir $candidate
        }
        if (Test-Path -LiteralPath $candidate) { return $candidate }
        Write-Error "`$$envKey 指向不存在的文件：$candidate"
        return $null
    }
    # 2) Bundled interpreters next to the pipeline (packaged layout).
    $bundled = @(
        (Join-Path $projectDir ".venv\Scripts\pythonw.exe"),
        (Join-Path $projectDir ".venv\Scripts\python.exe"),
        (Join-Path $projectDir "python\pythonw.exe"),
        (Join-Path $projectDir "pythonw.exe")
    )
    foreach ($candidate in $bundled) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    # 3) PATH lookup.
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python -ErrorAction SilentlyContinue }
    if ($cmd) { return $cmd.Source }
    return $null
}

$python = Resolve-PythonExe
if (-not $python) {
    Write-Error "未找到 Python 解释器：请设置 PYTHONW_EXE/PYTHON_EXE（绝对路径），或在 PATH 中提供 pythonw/python，然后重试。计划任务未注册。"
    exit 1
}
if ([System.IO.Path]::IsPathRooted($DbPath)) {
    $dbPath = $DbPath
} else {
    $dbPath = Join-Path $projectDir $DbPath
}
$argList = "tools/editorial_daily.py --db `"$dbPath`" --trigger scheduled"
$command = "$python $argList"

if ($Remove) {
    if ($DryRun) {
        Write-Host "would remove task: $TaskName"
        exit 0
    }
    schtasks /Delete /TN $TaskName /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to delete scheduled task $TaskName (schtasks exit code $LASTEXITCODE)."
        exit 1
    }
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
    -Description "novel-editorial 日更调度器（每天 $Time）" -Force
Write-Host "已注册计划任务 $TaskName，每天 $Time 运行。"

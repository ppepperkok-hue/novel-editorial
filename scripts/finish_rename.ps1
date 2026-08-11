<#
收尾改名：把项目目录 novel-pipeline 改名为 novel-editorial，并重建开机自启动。

注意：这个脚本不能在 Codex 运行时执行（Codex 进程占用旧目录句柄）。
请先完全退出 Codex，再在旧目录里运行：
  powershell -ExecutionPolicy Bypass -File scripts/finish_rename.ps1
#>

$ErrorActionPreference = "Stop"
Set-Location E:\code

$old = "E:\code\novel-pipeline"
$new = "E:\code\novel-editorial"

if (Test-Path $new) {
    Write-Host "新目录已存在：$new，中止（避免覆盖）。"
    exit 1
}
if (-not (Test-Path $old)) {
    Write-Host "旧目录不存在：$old，可能已经改过名。"
    exit 0
}

Rename-Item -LiteralPath $old -NewName "novel-editorial"
Write-Host "目录已改名为 $new"

$startup = [Environment]::GetFolderPath("Startup")
foreach ($legacy in @("NovelPipeline-api.vbs", "NovelPipeline-api.vbs.disabled")) {
    $p = Join-Path $startup $legacy
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Force
        Write-Host "已移除旧自启动：$p"
    }
}

Set-Location $new
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1
Write-Host "完成：目录已改名并注册新自启动（NovelEditorial-api.vbs）。"

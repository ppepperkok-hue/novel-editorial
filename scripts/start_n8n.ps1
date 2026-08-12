param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

# n8n 2.x disables executeCommand by default; the project's env file carries
# NODES_EXCLUDE=[] plus every pipeline variable ($env.* used in workflow
# expressions). Load all of them into the child process environment.
if (-not $EnvFile) {
    $EnvFile = Join-Path $env:USERPROFILE ".n8n\.env"
}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') {
            $name = $matches[1]
            $value = $matches[2].Trim()
            # Align with novel_editorial/config.py:_strip_inline_comment:
            # only a whitespace-preceded '#' starts a comment ('a=b#c' keeps
            # '#c'), and quotes stay part of the value (config keeps them).
            $cut = -1
            foreach ($sep in @(" #", "`t#")) {
                $idx = $value.IndexOf($sep)
                if ($idx -ge 0 -and ($cut -lt 0 -or $idx -lt $cut)) {
                    $cut = $idx
                }
            }
            if ($cut -ge 0) {
                $value = $value.Substring(0, $cut).Trim()
            }
            Set-Item -Path "Env:$name" -Value $value -ErrorAction SilentlyContinue
        }
    }
}

$nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $nodeExe) {
    Write-Host "node not found on PATH; set NODE_EXE to point at node.exe"
    exit 1
}
$n8nBin = Join-Path $env:APPDATA "npm\node_modules\n8n\bin\n8n"
Start-Process -FilePath $nodeExe `
    -ArgumentList $n8nBin `
    -WorkingDirectory $env:USERPROFILE `
    -WindowStyle Hidden
Write-Output "n8n starting with project env loaded"

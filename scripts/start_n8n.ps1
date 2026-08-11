param(
    [string]$EnvFile = "C:\Users\Administrator\.n8n\.env"
)

$ErrorActionPreference = "Stop"

# n8n 2.x disables executeCommand by default; the project's env file carries
# NODES_EXCLUDE=[] plus every pipeline variable ($env.* used in workflow
# expressions). Load all of them into the child process environment.
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') {
            $name = $matches[1]
            $value = $matches[2].Trim().Trim('"').Trim("'")
            Set-Item -Path "Env:$name" -Value $value -ErrorAction SilentlyContinue
        }
    }
}

$n8nBin = "C:\Users\Administrator\AppData\Roaming\npm\node_modules\n8n\bin\n8n"
Start-Process -FilePath "C:\Program Files\nodejs\node.exe" `
    -ArgumentList $n8nBin `
    -WorkingDirectory "C:\Users\Administrator" `
    -WindowStyle Hidden
Write-Output "n8n starting with project env loaded"

# OpsIQ MCP Quick Setup for PowerShell
$ErrorActionPreference = "Stop"

$ProjectRoot = (Get-Item $PSScriptRoot).Parent.FullName
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-Not (Test-Path $VenvPython)) {
    Write-Warning "Local .venv python not found at $VenvPython. Using system python."
    $VenvPython = "python"
}

Write-Host "Running OpsIQ MCP Installer using: $VenvPython" -ForegroundColor Cyan
& $VenvPython "$PSScriptRoot\setup_mcp.py"

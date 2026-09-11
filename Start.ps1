# N.E.H.A — PowerShell portable launcher (Windows)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "========================================"
Write-Host "  N.E.H.A — Multi-agent org desk"
Write-Host "========================================"
Write-Host "Portable Windows app. Set OPENAI_API_KEY in .env or GUI for live tool calling."
Write-Host ""

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "ERROR: Python not found on PATH. Install Python 3.11+ from python.org"
    exit 1
}

& python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python 3.11+ required"
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment .venv ..."
    python -m venv .venv
}

Write-Host "Installing / updating dependencies ..."
& ".venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
try {
    & ".venv\Scripts\python.exe" -m pip install -e ".[dev,desktop]"
} catch {
    & ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
}

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
}

Write-Host ""
Write-Host "Starting API + GUI at http://127.0.0.1:8000"
Write-Host "  Docs: http://127.0.0.1:8000/docs"

$hasWebview = $false
& ".venv\Scripts\python.exe" -c "import webview" 2>$null
if ($LASTEXITCODE -eq 0) { $hasWebview = $true }

if ($hasWebview) {
    & ".venv\Scripts\python.exe" -m grok_org_os.cli desktop --host 127.0.0.1 --port 8000
} else {
    Start-Job { Start-Sleep -Seconds 2; Start-Process "http://127.0.0.1:8000" } | Out-Null
    & ".venv\Scripts\python.exe" -m uvicorn grok_org_os.api.app:app --host 127.0.0.1 --port 8000
}

# 本机开发一键启动（SQLite + 内存 Redis，无需 Docker / 外部 Redis）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "Creating backend venv..."
    python -m venv (Join-Path $Backend ".venv")
    & $Py -m pip install -r (Join-Path $Backend "requirements.txt")
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "Installing frontend deps..."
    Push-Location $Frontend
    try {
        npm install
    } finally {
        Pop-Location
    }
}

$env:APP_ENV = "local"
$env:REDIS_URL = "memory://"
$env:DATABASE_URL = "sqlite+aiosqlite:///./quizgen.db"
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = "change-me-in-production"
}

Write-Host "Backend  http://127.0.0.1:8000"
Write-Host "Frontend http://127.0.0.1:3000"
Write-Host "Ctrl+C in each window to stop."

Start-Process powershell -WorkingDirectory $Backend -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$env:APP_ENV='local'; `$env:REDIS_URL='memory://'; `$env:DATABASE_URL='sqlite+aiosqlite:///./quizgen.db'; & '.\\.venv\\Scripts\\Activate.ps1'; uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)

Start-Process powershell -WorkingDirectory $Frontend -ArgumentList @(
    "-NoExit",
    "-Command",
    "npm run dev"
)

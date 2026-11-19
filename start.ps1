# TON Gift Terminal Pro — Скрипт швидкого запуску (Windows PowerShell)
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   TON Gift Terminal Pro — Запуск системи    " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[INFO] Створено файл .env з .env.example (режим DRY_RUN=True)" -ForegroundColor Yellow
}

if (-not (Test-Path "frontend\dist")) {
    Write-Host "[BUILD] Збираємо Mini App (frontend)..." -ForegroundColor Blue
    Push-Location frontend
    npm install
    npm run build
    Pop-Location
}

Write-Host "[START] Запускаємо Backend + Mini App + Telegram Bot на http://127.0.0.1:8000 ..." -ForegroundColor Green
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

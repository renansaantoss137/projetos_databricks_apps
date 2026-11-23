Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Iniciando Space Portal (BQ) em Modo Local..." -ForegroundColor Green
Write-Host "  URL: http://localhost:8080" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

Set-Location "$PSScriptRoot\src\app"
python app.py

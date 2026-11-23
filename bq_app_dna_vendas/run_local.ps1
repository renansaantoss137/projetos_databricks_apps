# Script para inicializar o DNA de Vendas localmente
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Inicializando DNA de Vendas (FastAPI)   " -ForegroundColor Cyan
Write-Host "  Acesse: http://127.0.0.1:8000           " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

Set-Location -Path "$PSScriptRoot\src\app"
& $PythonExe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload


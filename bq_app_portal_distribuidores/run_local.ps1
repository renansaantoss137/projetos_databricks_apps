# Script para inicializar o Portal de Distribuidores v2 localmente
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Inicializando Portal de Distribuidores v2 (Flask)       " -ForegroundColor Cyan
Write-Host "  Acesse: http://127.0.0.1:8000                           " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

Set-Location -Path "$PSScriptRoot\src\app"
& $PythonExe app.py

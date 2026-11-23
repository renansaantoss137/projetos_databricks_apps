# ============================================================
# BQ OTIF / Fill Rate - Script de Deploy do Databricks Bundle
# Grupo Bimbo Brasil - DNA Analytics
# 
# USO:
#   .\scripts\deploy.ps1            # Deploy em dev (padrao)
#   .\scripts\deploy.ps1 -Target dev
#   .\scripts\deploy.ps1 -Target prod
# ============================================================

param (
    [string]$Target = "dev"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Deploy BQ OTIF / Fill Rate -> Target: $Target" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if ($Target -eq "prod") {
    $APP_NAME   = "bq-oitf-fillrate"
    $APP_SOURCE = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/bq_app_oitf_fillrate/prod/files/src/app"
    $APP_URL    = "https://bq-oitf-fillrate-8674310331778219.19.azure.databricksapps.com"
} else {
    $APP_NAME   = "bq-oitf-fillrate-dev"
    $USER_NAME  = (databricks current-user me --output json | ConvertFrom-Json).userName
    $APP_SOURCE = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/$USER_NAME/bq_app_oitf_fillrate/dev/files/src/app"
    $APP_URL    = "https://bq-oitf-fillrate-dev-8674310331778219.19.azure.databricksapps.com"
}

# 1. Validar o bundle
Write-Host "`n[1/4] Validando configuracao do bundle ($Target)..." -ForegroundColor Yellow
databricks bundle validate -t $Target
if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro na validacao do bundle!" -ForegroundColor Red
    exit 1
}
Write-Host "Validacao concluida com sucesso." -ForegroundColor Green

# 2. Deploy do bundle (sincroniza arquivos e configura permissoes)
Write-Host "`n[2/4] Executando databricks bundle deploy ($Target)..." -ForegroundColor Yellow
databricks bundle deploy -t $Target
if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro no deploy do bundle!" -ForegroundColor Red
    exit 1
}
Write-Host "Bundle deployado com sucesso." -ForegroundColor Green

# 3. Garantir que o compute do app esteja ativo
Write-Host "`n[3/4] Verificando status do App Databricks ($APP_NAME)..." -ForegroundColor Yellow
$appJson = databricks apps get $APP_NAME --output json | ConvertFrom-Json
$computeState = $appJson.compute_status.state

if ($computeState -ne "ACTIVE") {
    Write-Host "Iniciando compute do app ($APP_NAME)..." -ForegroundColor Yellow
    databricks apps start $APP_NAME
}

# 4. Deploy do codigo do app
Write-Host "`n[4/4] Executando databricks apps deploy ($APP_NAME)..." -ForegroundColor Yellow
databricks apps deploy $APP_NAME --source-code-path $APP_SOURCE
if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro no deploy do app!" -ForegroundColor Red
    exit 1
}
Write-Host "App deployado com sucesso!" -ForegroundColor Green

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " App: $APP_NAME" -ForegroundColor Green
Write-Host " URL: $APP_URL" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
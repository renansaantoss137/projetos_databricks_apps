# ============================================================
# BQ Landing - Script de Deploy Completo
# Grupo Bimbo Brasil - DNA Analytics
# 
# USO: .\scripts\deploy.ps1
# 
# O que este script faz:
#   1. Baixa o base_landing.xlsx atual do Volume do Unity Catalog
#   2. Copia para src/app/base_landing.xlsx e fixtures/
#   3. Faz git commit da nova base
#   4. Executa databricks bundle deploy
#   5. Executa databricks apps deploy
# ============================================================

$VOLUME_PATH = "dbfs:/Volumes/cat_dnabb_dv/grobbbqb_sz/dev_bq_landing/base_landing.xlsx"
$APP_NAME    = "bq-landing-dev"
$APP_SOURCE  = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/bq_app_landing/dev/files/src/app"

Write-Host "`n?? [1/4] Sincronizando base_landing.xlsx do Volume..." -ForegroundColor Cyan
databricks fs cp $VOLUME_PATH "volume_sync_temp.xlsx" --overwrite -p DEFAULT
if ($LASTEXITCODE -ne 0) {
    Write-Host "? Erro ao baixar arquivo do Volume." -ForegroundColor Red
    exit 1
}
Copy-Item "volume_sync_temp.xlsx" "src/app/base_landing.xlsx" -Force
Copy-Item "volume_sync_temp.xlsx" "fixtures/base_landing.xlsx" -Force
Remove-Item "volume_sync_temp.xlsx" -Force
Write-Host "? base_landing.xlsx atualizado." -ForegroundColor Green

Write-Host "`n?? [2/4] Commitando base atualizada no git..." -ForegroundColor Cyan
$DATE = Get-Date -Format "yyyy-MM-dd HH:mm"
git add src/app/base_landing.xlsx fixtures/base_landing.xlsx
git commit -m "chore: sync base_landing.xlsx com volume ($DATE)" --allow-empty
Write-Host "? Commit feito." -ForegroundColor Green

Write-Host "`n?? [3/4] Databricks Bundle Deploy..." -ForegroundColor Cyan
databricks bundle deploy -t dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "? Erro no bundle deploy." -ForegroundColor Red
    exit 1
}
Write-Host "? Bundle deployado." -ForegroundColor Green

Write-Host "`n?? [4/4] Databricks App Deploy ($APP_NAME)..." -ForegroundColor Cyan
databricks apps deploy $APP_NAME --source-code-path $APP_SOURCE
if ($LASTEXITCODE -ne 0) {
    Write-Host "? Erro no app deploy." -ForegroundColor Red
    exit 1
}
Write-Host "? App deployado com sucesso!" -ForegroundColor Green

Write-Host "`n?? App disponivel em:" -ForegroundColor Yellow
Write-Host "   https://bq-landing-dev-8674310331778219.19.azure.databricksapps.com`n" -ForegroundColor White

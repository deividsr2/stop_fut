# Script de Inicialização Completa do StopFut
Write-Host "============================================================" -ForegroundColor Green
Write-Host "         INICIANDO STOPFUT (ADEDONHA DO FUTEBOL)            " -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green

# 1. Verifica se o AWS Emulator está respondendo
Write-Host "`n1. Verificando conexao com AWS Emulator na porta 9297..." -ForegroundColor Cyan
try {
    $res = Invoke-RestMethod -Uri "https://127.0.0.1:9297/__admin/health" -SkipCertificateCheck -TimeoutSec 3
    Write-Host "   [OK] AWS Emulator operacional!" -ForegroundColor Green
} catch {
    Write-Host "   [AVISO] Verifique se o container 'aws-emulator' esta ativo." -ForegroundColor Yellow
}

# 2. Deploy no S3 (Bucket stopfut-web)
Write-Host "`n2. Realizando deploy dos arquivos estaticos no Amazon S3..." -ForegroundColor Cyan
python stop_fut\deploy_s3.py

# 3. Inicia o Servidor Backend (porta 8080)
Write-Host "`n3. Iniciando Servidor Backend e Agente de Validacao..." -ForegroundColor Cyan
Write-Host "   Acesse a aplicacao em: http://localhost:8080" -ForegroundColor Green
Write-Host "   Pressione Ctrl+C a qualquer momento para encerrar." -ForegroundColor Gray

# Abre o navegador automaticamente
Start-Process "http://localhost:8080"

# Inicia o servidor em primeiro plano
python stop_fut\backend\server.py

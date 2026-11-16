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
    Write-Host "   [AVISO] Verifique se o container 'aws-emulator' esta ativo no Docker." -ForegroundColor Yellow
}

# 2. Verifica se a tabela no DynamoDB existe; caso contrário, popula automaticamente
Write-Host "`n2. Verificando banco de dados no DynamoDB..." -ForegroundColor Cyan
$dbCheck = python -c "
from stop_fut.backend.agent_validator import FootballAgentValidator
v = FootballAgentValidator()
tables = v.client.list_tables().get('TableNames', [])
print('READY' if 'stopfut_database' in tables else 'NEED_BUILD')
"
if ($dbCheck -match "NEED_BUILD") {
    Write-Host "   -> Criando tabela e populando base inicial..." -ForegroundColor Yellow
    python stop_fut\backend\build_database.py
    Write-Host "   -> Importando dataset global Transfermarkt..." -ForegroundColor Yellow
    python stop_fut\backend\import_global_transfermarkt.py
    Write-Host "   [OK] Banco DynamoDB populado com sucesso!" -ForegroundColor Green
} else {
    Write-Host "   [OK] Banco DynamoDB ja esta pronto e populado!" -ForegroundColor Green
}

# 3. Deploy no S3 (Bucket stopfut-web)
Write-Host "`n3. Realizando deploy dos arquivos estaticos no Amazon S3..." -ForegroundColor Cyan
python stop_fut\deploy_s3.py

# 4. Inicia o Servidor Backend (porta 8080)
Write-Host "`n4. Iniciando Servidor Backend e Agente de Validacao..." -ForegroundColor Cyan
Write-Host "   Acesse a aplicacao em: http://localhost:8080" -ForegroundColor Green
Write-Host "   Pressione Ctrl+C a qualquer momento para encerrar." -ForegroundColor Gray

# Abre o navegador automaticamente
Start-Process "http://localhost:8080"

# Inicia o servidor em primeiro plano
python stop_fut\backend\server.py

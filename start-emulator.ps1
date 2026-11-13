# Script para iniciar o AWS Emulator Oficial via Docker Compose
Write-Host "Construindo e iniciando container do AWS Emulator..." -ForegroundColor Cyan
docker compose up -d --build

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nAWS Emulator iniciado com sucesso em https://127.0.0.1:9297" -ForegroundColor Green
    Write-Host "Aguardando geracao dos certificados e credenciais..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    
    # Executa a suite de testes Python
    python test_emulator.py
} else {
    Write-Host "`nErro ao iniciar. Certifique-se de que o Docker Desktop esta aberto e executando." -ForegroundColor Red
}

# Configura as variáveis de ambiente necessárias para o AWS CLI ou SDKs locais
$port = 9297
$env:AWS_ENDPOINT_URL = "https://127.0.0.1:$port"
$env:AWS_SHARED_CREDENTIALS_FILE = "$env:USERPROFILE\.aws\emulator\$port\emulator_credentials"
$env:AWS_CONFIG_FILE = "$env:USERPROFILE\.aws\emulator\$port\config"
$env:AWS_CA_BUNDLE = "$env:USERPROFILE\.aws\emulator\$port\ca.pem"
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_DEFAULT_REGION = "us-east-1"

Write-Host "Variaveis de ambiente para o AWS Emulator (porta $port) configuradas nesta sessao!" -ForegroundColor Green
Write-Host "Endpoint: $env:AWS_ENDPOINT_URL"
Write-Host "Certificado CA: $env:AWS_CA_BUNDLE"

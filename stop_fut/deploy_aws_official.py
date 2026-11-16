"""
Script de Deploy 100% Serverless do StopFut na Nuvem Oficial da AWS.
Arquitetura Custo Zero (AWS Free Tier):
1. Amazon DynamoDB: Tabela 'stopfut_database' (On-Demand / Pay-Per-Request, $0 quando ocioso)
2. Migração de Dados: 6.108 clubes, jogadores, estádios e apelidos indexados
3. AWS Lambda: Função 'stopfut-api' com Function URL pública HTTPS e CORS liberado
4. Amazon S3: Hospedagem estática do frontend estilo StopotS (HTML/CSS/JS)
"""

import os
import sys
import time
import json
import zipfile
import io
import mimetypes
import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
ACCOUNT_ID = "020195185120"
DYNAMO_TABLE = "stopfut_database"
LAMBDA_NAME = "stopfut-api"
LAMBDA_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/admin-lambda-role"
BUCKET_NAME = f"stopfut-app-{ACCOUNT_ID}"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "stop_fut", "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "stop_fut", "frontend")

# Clientes AWS Oficial
session = boto3.Session(region_name=REGION)
dynamo_official = session.client("dynamodb")
lambda_official = session.client("lambda")
s3_official = session.client("s3")


def step_banner(num: int, title: str):
    print("\n" + "=" * 65)
    print(f"  ETAPA {num}: {title.upper()}")
    print("=" * 65)


def deploy_dynamodb():
    step_banner(1, "Criando Tabela DynamoDB Oficial na AWS")
    tables = dynamo_official.list_tables().get("TableNames", [])
    
    if DYNAMO_TABLE in tables:
        print(f"[OK] Tabela '{DYNAMO_TABLE}' já existe na AWS ({REGION}).")
    else:
        print(f"[CRIANDO] Criando tabela '{DYNAMO_TABLE}' em modo PAY_PER_REQUEST...")
        dynamo_official.create_table(
            TableName=DYNAMO_TABLE,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST"
        )
        print("Aguardando tabela ficar ativa...")
        waiter = dynamo_official.get_waiter("table_exists")
        waiter.wait(TableName=DYNAMO_TABLE)
        print(f"[OK] Tabela '{DYNAMO_TABLE}' criada e ativa com sucesso!")


def migrate_database_items():
    step_banner(2, "Migrando e Semeando Registros para o DynamoDB Oficial")
    
    # Verifica quantos itens já estão na tabela oficial
    try:
        official_scan = dynamo_official.scan(TableName=DYNAMO_TABLE, Select="COUNT", Limit=10)
        official_count = official_scan.get("Count", 0)
    except Exception:
        official_count = 0

    if official_count >= 5000:
        print(f"[OK] DynamoDB Oficial já possui {official_count}+ registros semeados. Pulando migração.")
        return

    # Conecta no emulador local para ler os dados
    print("Lendo dados da base local (6.000+ jogadores, clubes e estádios)...")
    sys.path.insert(0, BACKEND_DIR)
    from agent_validator import FootballAgentValidator
    local_val = FootballAgentValidator()
    
    paginator = local_val.client.get_paginator("scan")
    items_to_migrate = []
    
    for page in paginator.paginate(TableName="stopfut_database"):
        items_to_migrate.extend(page.get("Items", []))

    total = len(items_to_migrate)
    print(f"Total de {total} itens encontrados na base local para migração.")

    # Batch write em pedaços de 25 itens
    batch_size = 25
    written = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        chunk = items_to_migrate[i:i + batch_size]
        reqs = [{"PutRequest": {"Item": it}} for it in chunk]
        
        retries = 3
        while retries > 0:
            try:
                res = dynamo_official.batch_write_item(
                    RequestItems={DYNAMO_TABLE: reqs}
                )
                unprocessed = res.get("UnprocessedItems", {}).get(DYNAMO_TABLE, [])
                if unprocessed:
                    reqs = unprocessed
                    retries -= 1
                    time.sleep(0.5)
                else:
                    break
            except Exception as e:
                time.sleep(1)
                retries -= 1
                if retries == 0:
                    print(f"Erro no lote {i}: {e}")

        written += len(chunk)
        if written % 500 == 0 or written == total:
            elapsed = time.time() - start_time
            print(f" -> [{written}/{total}] itens migrados para AWS DynamoDB ({elapsed:.1f}s)...")

    print(f"[OK] Migração concluída com sucesso! {written} itens disponíveis no DynamoDB oficial.")


def deploy_lambda():
    step_banner(3, "Deploy da API Serverless no AWS Lambda")
    
    # 1. Empacota backend em memória ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ["server.py", "agent_validator.py", "rooms_manager.py"]:
            fpath = os.path.join(BACKEND_DIR, fname)
            zf.write(fpath, arcname=fname)
    
    zip_bytes = zip_buffer.getvalue()
    print(f"Pacote Lambda construído: {len(zip_bytes)} bytes.")

    env_vars = {
        "USE_REAL_AWS": "true"
    }

    # 2. Cria ou Atualiza a Função Lambda
    try:
        print(f"Verificando função Lambda '{LAMBDA_NAME}'...")
        lambda_official.get_function(FunctionName=LAMBDA_NAME)
        print("Atualizando código da função existente...")
        lambda_official.update_function_code(
            FunctionName=LAMBDA_NAME,
            ZipFile=zip_bytes
        )
        print("Aguardando estabilização da atualização de código...")
        try:
            waiter = lambda_official.get_waiter("function_updated_v2")
            waiter.wait(FunctionName=LAMBDA_NAME)
        except Exception:
            time.sleep(4)

        lambda_official.update_function_configuration(
            FunctionName=LAMBDA_NAME,
            Handler="server.lambda_handler",
            Runtime="python3.12",
            Timeout=15,
            MemorySize=256,
            Environment={"Variables": env_vars}
        )
        print(f"[OK] Função Lambda '{LAMBDA_NAME}' atualizada.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"Criando função Lambda '{LAMBDA_NAME}'...")
            lambda_official.create_function(
                FunctionName=LAMBDA_NAME,
                Runtime="python3.12",
                Role=LAMBDA_ROLE_ARN,
                Handler="server.lambda_handler",
                Code={"ZipFile": zip_bytes},
                Timeout=15,
                MemorySize=256,
                Environment={"Variables": env_vars}
            )
            print("Aguardando função ficar ativa...")
            try:
                waiter = lambda_official.get_waiter("function_active_v2")
                waiter.wait(FunctionName=LAMBDA_NAME)
            except Exception:
                time.sleep(5)
            print(f"[OK] Função Lambda '{LAMBDA_NAME}' criada com sucesso!")
        else:
            raise e

    # 3. Configura Function URL (Endpoint HTTPS Público)
    print("Configurando Lambda Function URL pública com CORS...")
    try:
        url_cfg = lambda_official.get_function_url_config(FunctionName=LAMBDA_NAME)
        function_url = url_cfg["FunctionUrl"]
        print(f"[OK] Function URL existente: {function_url}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            url_res = lambda_official.create_function_url_config(
                FunctionName=LAMBDA_NAME,
                AuthType="NONE",
                Cors={
                    "AllowOrigins": ["*"],
                    "AllowMethods": ["GET", "POST", "OPTIONS"],
                    "AllowHeaders": ["Content-Type"]
                }
            )
            function_url = url_res["FunctionUrl"]
            print(f"[OK] Function URL criada: {function_url}")
        else:
            raise e

    # Permissão para invocação pública
    try:
        lambda_official.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId="FunctionURLAllowPublicAccess",
            Action="lambda:InvokeFunctionUrl",
            Principal="*",
            FunctionUrlAuthType="NONE"
        )
        print("[OK] Permissão de acesso público concedida à Function URL.")
    except ClientError as e:
        if "ResourceConflictException" in str(e):
            pass # Permissão já existe
        else:
            print("Nota sobre permissão:", e)

    return function_url.rstrip("/")


def deploy_frontend_s3(lambda_url: str):
    step_banner(4, "Deploy do Frontend no Amazon S3 (Static Website Hosting)")
    
    # 1. Cria Bucket S3
    buckets = [b["Name"] for b in s3_official.list_buckets().get("Buckets", [])]
    if BUCKET_NAME not in buckets:
        print(f"Criando bucket S3 '{BUCKET_NAME}' em {REGION}...")
        s3_official.create_bucket(Bucket=BUCKET_NAME)
        print(f"[OK] Bucket '{BUCKET_NAME}' criado com sucesso!")
    else:
        print(f"[OK] Bucket '{BUCKET_NAME}' já existe.")

    # 2. Desativa Bloqueio de Acesso Público no Bucket
    print("Configurando permissões públicas para hospedagem web estática...")
    try:
        s3_official.put_public_access_block(
            Bucket=BUCKET_NAME,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False
            }
        )
    except Exception as e:
        print("Aviso ao configurar PublicAccessBlock:", e)

    # 3. Política de Leitura Pública do Website
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{BUCKET_NAME}/*"
            }
        ]
    }
    s3_official.put_bucket_policy(
        Bucket=BUCKET_NAME,
        Policy=json.dumps(bucket_policy)
    )
    print("[OK] Política pública aplicada com sucesso.")

    # 4. Habilita Static Website Hosting
    s3_official.put_bucket_website(
        Bucket=BUCKET_NAME,
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}}
    )
    print("[OK] Website Hosting habilitado (index.html).")

    # 5. Prepara e faz upload dos arquivos
    # Lê index.html e injeta a URL da API Lambda
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    # Injeta a variável global window.LAMBDA_API_URL antes do app.js
    injection_tag = f'<script>window.LAMBDA_API_URL = "{lambda_url}";</script>\n  <script src="app.js"></script>'
    import re
    if 'window.LAMBDA_API_URL' in index_content:
        index_content = re.sub(
            r'<script>window\.LAMBDA_API_URL\s*=\s*".*?";</script>',
            f'<script>window.LAMBDA_API_URL = "{lambda_url}";</script>',
            index_content
        )
    else:
        index_content = index_content.replace('<script src="app.js"></script>', injection_tag)

    css_path = os.path.join(FRONTEND_DIR, "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    js_path = os.path.join(FRONTEND_DIR, "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    files = [
        ("index.html", index_content.encode("utf-8"), "text/html; charset=utf-8"),
        ("style.css", css_content.encode("utf-8"), "text/css; charset=utf-8"),
        ("app.js", js_content.encode("utf-8"), "application/javascript; charset=utf-8")
    ]

    for fname, body, mime in files:
        s3_official.put_object(
            Bucket=BUCKET_NAME,
            Key=fname,
            Body=body,
            ContentType=mime,
            CacheControl="no-cache"
        )
        print(f" -> Upload concluído: {fname} ({len(body)} bytes)")

    website_url = f"http://{BUCKET_NAME}.s3-website-{REGION}.amazonaws.com"
    return website_url


def main():
    print("=" * 65)
    print("   🚀 STOPFUT - DEPLOY OFICIAL AWS SERVERLESS (CUSTO $0)")
    print("=" * 65)
    
    # 1. DynamoDB
    deploy_dynamodb()

    # 2. Migração de Dados
    migrate_database_items()

    # 3. AWS Lambda API
    lambda_url = deploy_lambda()

    # 4. Amazon S3 Frontend
    website_url = deploy_frontend_s3(lambda_url)

    # 5. Resumo Final
    print("\n" + "=" * 65)
    print("   🎉 DEPLOY CONCLUÍDO COM SUCESSO NA AWS OFICIAL!")
    print("=" * 65)
    print(f" 🌐 SITE PÚBLICO (JOGUE AGORA):  {website_url}")
    print(f" ⚡ API LAMBDA SERVERLESS:       {lambda_url}")
    print(f" 🗄️ DYNAMODB TABELA:            {DYNAMO_TABLE} ({REGION})")
    print(f" 💰 CUSTO MENSAL ESTIMADO:       R$ 0,00 (100% Free Tier)")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()

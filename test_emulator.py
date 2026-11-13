"""
Script de teste para o AWS Emulator oficial da AWS.
Valida operações em múltiplos serviços da AWS usando boto3:
- STS (GetCallerIdentity)
- S3 (CreateBucket, PutObject, GetObject, ListBuckets)
- DynamoDB (CreateTable, PutItem, GetItem)
- SQS (CreateQueue, SendMessage, ReceiveMessage, DeleteMessage)
- Secrets Manager (CreateSecret, GetSecretValue)
"""

import os
import sys
import configparser
import boto3
from botocore.config import Config

EMULATOR_URL = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
HOME = os.path.expanduser("~")
EMULATOR_DIR = os.path.join(HOME, ".aws", "emulator", "9297")

# Carrega credenciais geradas pelo emulador
access_key = os.environ.get("AWS_ACCESS_KEY_ID")
secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

creds_file = os.environ.get("AWS_SHARED_CREDENTIALS_FILE", os.path.join(EMULATOR_DIR, "emulator_credentials"))
if os.path.exists(creds_file):
    cfg = configparser.ConfigParser()
    cfg.read(creds_file)
    if "default" in cfg:
        access_key = cfg["default"].get("aws_access_key_id", access_key)
        secret_key = cfg["default"].get("aws_secret_access_key", secret_key)
        print(f"[OK] Credenciais carregadas de: {creds_file} (Key: {access_key[:8]}...)")

if not access_key:
    access_key = "test"
    secret_key = "test"

# Certificado SSL CA gerado pelo emulador
ca_bundle = os.environ.get("AWS_CA_BUNDLE", os.path.join(EMULATOR_DIR, "ca.pem"))
if os.path.exists(ca_bundle):
    verify_ssl = ca_bundle
    print(f"[OK] Certificado CA carregado de: {ca_bundle}")
else:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    verify_ssl = False
    print(f"[AVISO] ca.pem nao encontrado em {ca_bundle}. Desativando validacao SSL.")

boto_config = Config(
    region_name="us-east-1",
    s3={"addressing_style": "path"}
)

session = boto3.Session(
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name="us-east-1"
)

print(f"\n--> Conectando ao AWS Emulator em: {EMULATOR_URL}\n")

def test_sts():
    print("--- 1. Testando AWS STS ---")
    sts = session.client("sts", endpoint_url=EMULATOR_URL, verify=verify_ssl, config=boto_config)
    try:
        identity = sts.get_caller_identity()
        print(f"  [STS OK] Account: {identity.get('Account')}")
        print(f"  [STS OK] UserId:  {identity.get('UserId')}")
        print(f"  [STS OK] Arn:     {identity.get('Arn')}")
        return True
    except Exception as e:
        print(f"  [STS FALHA] {e}")
        return False

def test_s3():
    print("\n--- 2. Testando AWS S3 ---")
    s3 = session.client("s3", endpoint_url=EMULATOR_URL, verify=verify_ssl, config=boto_config)
    bucket_name = "meu-bucket-local"
    key_name = "documento-teste.txt"
    payload = "Conteudo de teste no AWS Emulator Oficial!"

    try:
        # Criação de Bucket (se não existir)
        buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
        if bucket_name not in buckets:
            s3.create_bucket(Bucket=bucket_name)
            print(f"  [S3 OK] Bucket '{bucket_name}' criado com sucesso.")
        else:
            print(f"  [S3 OK] Bucket '{bucket_name}' ja existente.")

        # Upload de Objeto
        s3.put_object(Bucket=bucket_name, Key=key_name, Body=payload.encode("utf-8"))
        print(f"  [S3 OK] Objeto '{key_name}' gravado.")

        # Download / Leitura do Objeto
        obj = s3.get_object(Bucket=bucket_name, Key=key_name)
        conteudo = obj["Body"].read().decode("utf-8")
        print(f"  [S3 OK] Objeto lido com sucesso: \"{conteudo}\"")

        # Listagem de Buckets
        res = s3.list_buckets()
        nomes = [b["Name"] for b in res.get("Buckets", [])]
        print(f"  [S3 OK] Buckets ativos: {nomes}")
        return True
    except Exception as e:
        print(f"  [S3 FALHA] {e}")
        return False

def test_dynamodb():
    print("\n--- 3. Testando Amazon DynamoDB ---")
    dynamo = session.client("dynamodb", endpoint_url=EMULATOR_URL, verify=verify_ssl, config=boto_config)
    table_name = "Clientes"

    try:
        # Criar Tabela (se já não existir)
        existing = dynamo.list_tables().get("TableNames", [])
        if table_name not in existing:
            dynamo.create_table(
                TableName=table_name,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST"
            )
            print(f"  [DynamoDB OK] Tabela '{table_name}' criada.")
        else:
            print(f"  [DynamoDB OK] Tabela '{table_name}' ja existe.")

        # Aguarda a tabela ficar ACTIVE (comportamento padrão da AWS)
        print("  [DynamoDB] Aguardando status ACTIVE...")
        waiter = dynamo.get_waiter("table_exists")
        waiter.wait(TableName=table_name)
        print("  [DynamoDB OK] Tabela pronta (ACTIVE).")

        # Inserir Item
        dynamo.put_item(
            TableName=table_name,
            Item={
                "id": {"S": "cli-001"},
                "nome": {"S": "Empresa ABC Ltda"},
                "status": {"S": "ATIVO"}
            }
        )
        print("  [DynamoDB OK] Registro inserido na tabela.")

        # Consultar Item
        item = dynamo.get_item(TableName=table_name, Key={"id": {"S": "cli-001"}}).get("Item", {})
        print(f"  [DynamoDB OK] Registro recuperado: id={item.get('id', {}).get('S')}, nome={item.get('nome', {}).get('S')}")
        return True
    except Exception as e:
        print(f"  [DynamoDB FALHA] {e}")
        return False

def test_sqs():
    print("\n--- 4. Testando Amazon SQS ---")
    sqs = session.client("sqs", endpoint_url=EMULATOR_URL, verify=verify_ssl, config=boto_config)
    queue_name = "pedidos-processamento"

    try:
        # Criar fila
        res = sqs.create_queue(QueueName=queue_name)
        queue_url = res["QueueUrl"]
        print(f"  [SQS OK] Fila criada: {queue_url}")

        # Enviar mensagem
        sqs.send_message(QueueUrl=queue_url, MessageBody="Pedido #1004 aprovado")
        print("  [SQS OK] Mensagem enviada para a fila.")

        # Receber mensagem
        recv = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)
        msgs = recv.get("Messages", [])
        if msgs:
            m = msgs[0]
            print(f"  [SQS OK] Mensagem recebida: \"{m.get('Body')}\"")
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
            print("  [SQS OK] Mensagem confirmada e removida da fila.")
        return True
    except Exception as e:
        print(f"  [SQS FALHA] {e}")
        return False

def test_secrets_manager():
    print("\n--- 5. Testando AWS Secrets Manager ---")
    sm = session.client("secretsmanager", endpoint_url=EMULATOR_URL, verify=verify_ssl, config=boto_config)
    import time
    secret_name = f"app/db/password-{int(time.time())}"
    try:
        sm.create_secret(Name=secret_name, SecretString="super-secret-password-123")
        print(f"  [SecretsManager OK] Segredo '{secret_name}' criado.")

        val = sm.get_secret_value(SecretId=secret_name)
        print(f"  [SecretsManager OK] Segredo recuperado: \"{val.get('SecretString')}\"")
        return True
    except Exception as e:
        print(f"  [SecretsManager FALHA ou 501] {e}")
        return False

def test_sns():
    print("\n--- 6. Testando Amazon SNS ---")
    sns = session.client("sns", endpoint_url=EMULATOR_URL, verify=verify_ssl, config=boto_config)
    topic_name = "notificacoes-sistema"
    try:
        topic = sns.create_topic(Name=topic_name)
        arn = topic["TopicArn"]
        print(f"  [SNS OK] Topico criado: {arn}")

        pub = sns.publish(TopicArn=arn, Message="Alerta de teste via AWS Emulator", Subject="Alerta")
        print(f"  [SNS OK] Mensagem publicada (MessageId: {pub.get('MessageId')})")
        return True
    except Exception as e:
        print(f"  [SNS FALHA] {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("   Bateria de Testes: AWS Emulator Oficial (Porta 9297)")
    print("=" * 60)

    sts_ok = test_sts()
    s3_ok = test_s3()
    dynamo_ok = test_dynamodb()
    sqs_ok = test_sqs()
    sm_ok = test_secrets_manager()
    sns_ok = test_sns()

    print("\n" + "=" * 60)
    print("   RESULTADO DA BATERIA DE TESTES")
    print("=" * 60)
    print(f"   STS:             {'[PASSOU]' if sts_ok else '[FALHOU]'}")
    print(f"   S3:              {'[PASSOU]' if s3_ok else '[FALHOU]'}")
    print(f"   DynamoDB:        {'[PASSOU]' if dynamo_ok else '[FALHOU]'}")
    print(f"   SQS:             {'[PASSOU]' if sqs_ok else '[FALHOU]'}")
    print(f"   Secrets Manager: {'[PASSOU]' if sm_ok else '[FALHOU]'}")
    print(f"   SNS:             {'[PASSOU]' if sns_ok else '[FALHOU]'}")
    print("=" * 60)

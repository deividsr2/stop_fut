"""
Script para Implantação do Frontend do StopFut no Amazon S3 (AWS Emulator Oficial).
Cria o bucket 'stopfut-web', ativa a hospedagem estática de site
e realiza o upload dos arquivos index.html, style.css e app.js.
"""

import os
import mimetypes
import configparser
import boto3
from botocore.config import Config

EMULATOR_URL = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
HOME = os.path.expanduser("~")
EMULATOR_DIR = os.path.join(HOME, ".aws", "emulator", "9297")
BUCKET_NAME = "stopfut-web"
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend"))

def get_s3_client():
    creds_file = os.path.join(EMULATOR_DIR, "emulator_credentials")
    ca_bundle = os.path.join(EMULATOR_DIR, "ca.pem")
    
    key, secret = "test", "test"
    if os.path.exists(creds_file):
        cfg = configparser.ConfigParser()
        cfg.read(creds_file)
        if "default" in cfg:
            key = cfg["default"].get("aws_access_key_id", key)
            secret = cfg["default"].get("aws_secret_access_key", secret)

    verify = ca_bundle if os.path.exists(ca_bundle) else False
    if not verify:
        import urllib3
        urllib3.disable_warnings()

    return boto3.client(
        "s3",
        endpoint_url=EMULATOR_URL,
        verify=verify,
        region_name="us-east-1",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=Config(s3={"addressing_style": "path"})
    )

def deploy():
    print("=" * 60)
    print("   DEPLOY DO STOPFUT NO AMAZON S3 (AWS EMULATOR)")
    print("=" * 60)

    s3 = get_s3_client()

    # 1. Cria o Bucket se não existir
    buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if BUCKET_NAME not in buckets:
        print(f"Criando bucket '{BUCKET_NAME}' no S3...")
        s3.create_bucket(Bucket=BUCKET_NAME)
        print("Bucket criado com sucesso!")
    else:
        print(f"Bucket '{BUCKET_NAME}' já existente.")

    # 2. Configura S3 Static Website Hosting
    print("Configurando Static Website Hosting (IndexDocument: index.html)...")
    try:
        s3.put_bucket_website(
            Bucket=BUCKET_NAME,
            WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}}
        )
        print("Website hosting habilitado com sucesso!")
    except Exception as e:
        print(f"Aviso ao configurar website hosting: {e}")

    # 3. Upload dos arquivos estáticos
    files_to_upload = ["index.html", "style.css", "app.js"]
    for filename in files_to_upload:
        filepath = os.path.join(FRONTEND_DIR, filename)
        if not os.path.exists(filepath):
            print(f"[ERRO] Arquivo não encontrado: {filepath}")
            continue

        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type:
            if filename.endswith(".css"):
                mime_type = "text/css"
            elif filename.endswith(".js"):
                mime_type = "application/javascript"
            else:
                mime_type = "text/html"

        with open(filepath, "rb") as f:
            body = f.read()

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=filename,
            Body=body,
            ContentType=f"{mime_type}; charset=utf-8"
        )
        print(f" -> Upload concluído: {filename} ({len(body)} bytes, {mime_type})")

    print("\n" + "=" * 60)
    print(f"   DEPLOY NO S3 CONCLUÍDO COM SUCESSO!")
    print(f"   Bucket: s3://{BUCKET_NAME}/")
    print(f"   Objetos: {files_to_upload}")
    print("=" * 60)

if __name__ == "__main__":
    deploy()

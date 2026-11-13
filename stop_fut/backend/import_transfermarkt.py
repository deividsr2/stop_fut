"""
Script para Importação e Enriquecimento do StopFut a partir do Datalake Transfermarkt:
https://github.com/salimt/football-datasets/tree/main/datalake/transfermarkt

Baixa o player_profiles.csv (92.671 jogadores), filtra atletas brasileiros
e estrelas mundiais, traduz as posições táticas exatas (Lateral Esquerdo, etc.)
e grava em lotes no Amazon DynamoDB do AWS Emulator.
"""

import os
import re
import csv
import io
import time
import unicodedata
import configparser
import urllib.request
import boto3
from botocore.config import Config

EMULATOR_URL = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
HOME = os.path.expanduser("~")
EMULATOR_DIR = os.path.join(HOME, ".aws", "emulator", "9297")
TABLE_NAME = "stopfut_database"

PROFILES_URL = "https://raw.githubusercontent.com/salimt/football-datasets/main/datalake/transfermarkt/player_profiles/player_profiles.csv"

POSITION_MAP = {
    "Defender - Left-Back": ("Lateral", "Lateral Esquerdo"),
    "Defender - Right-Back": ("Lateral", "Lateral Direito"),
    "Defender - Centre-Back": ("Zagueiro", "Zagueiro"),
    "Defender - Sweeper": ("Zagueiro", "Líbero"),
    "Defender": ("Defensor", "Defensor"),
    "Midfield - Defensive Midfield": ("Meia", "Volante"),
    "Midfield - Central Midfield": ("Meia", "Meio-campo"),
    "Midfield - Attacking Midfield": ("Meia", "Meia-atacante"),
    "Midfield - Left Midfield": ("Meia", "Meia-esquerda"),
    "Midfield - Right Midfield": ("Meia", "Meia-direita"),
    "Midfield": ("Meia", "Meio-campo"),
    "Attack - Centre-Forward": ("Atacante", "Centroavante"),
    "Attack - Second Striker": ("Atacante", "Segundo Atacante"),
    "Attack - Left Winger": ("Atacante", "Ponta Esquerda"),
    "Attack - Right Winger": ("Atacante", "Ponta Direita"),
    "Attack": ("Atacante", "Atacante"),
    "Goalkeeper": ("Goleiro", "Goleiro")
}

TOP_NATIONS = {
    "Brazil", "Argentina", "France", "Germany", "Spain", "England",
    "Italy", "Netherlands", "Portugal", "Uruguay", "Colombia", "Belgium"
}

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
    return text.strip().lower()

def clean_name(raw_name: str) -> str:
    # Remove sufixo do ID, ex: "Ruud van Nistelrooy (3407)" -> "Ruud van Nistelrooy"
    return re.sub(r"\s*\(\d+\)$", "", raw_name).strip()

def get_dynamo_client():
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
        "dynamodb",
        endpoint_url=EMULATOR_URL,
        verify=verify,
        region_name="us-east-1",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=Config(retries={"max_attempts": 3, "mode": "standard"})
    )

def batch_write(client, items):
    chunks = [items[i:i + 25] for i in range(0, len(items), 25)]
    written = 0
    for chunk in chunks:
        req_items = [
            {"PutRequest": {"Item": {k: {"S": str(v)} for k, v in it.items() if v is not None and str(v).strip() != ""}}}
            for it in chunk
        ]
        client.batch_write_item(RequestItems={TABLE_NAME: req_items})
        written += len(chunk)
    return written

def import_transfermarkt_dataset():
    print("=" * 65)
    print("   IMPORTAÇÃO DO DATALAKE TRANSFERMARKT (salimt/football-datasets)")
    print("=" * 65)
    
    client = get_dynamo_client()
    print("Conectado ao DynamoDB local.")
    print("Baixando e processando player_profiles.csv...")

    req = urllib.request.Request(PROFILES_URL, headers={"User-Agent": "Mozilla/5.0"})
    
    items = []
    seen = set()
    total_rows = 0
    selected_players = 0

    t0 = time.time()
    with urllib.request.urlopen(req, timeout=30) as resp:
        reader = csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8", errors="ignore"))
        for row in reader:
            total_rows += 1
            country = row.get("citizenship", "")
            club = row.get("current_club_name", "").strip()
            pos_raw = row.get("position", "")

            # Prioriza brasileiros e jogadores das principais seleções do futebol mundial
            is_brazilian = (country == "Brazil")
            is_top_nation = (country in TOP_NATIONS)
            is_active_or_legend = (club != "" and club != "Retired") or (row.get("player_agent_name") != "")

            if not (is_brazilian or (is_top_nation and is_active_or_legend)):
                continue

            pos_gen, pos_det = POSITION_MAP.get(pos_raw, ("Jogador", "Jogador"))
            full_name = clean_name(row.get("player_name", ""))
            home_name = row.get("name_in_home_country", "").strip()
            slug_name = row.get("player_slug", "").replace("-", " ").strip()

            if not full_name or len(full_name) < 2:
                continue

            names_to_index = {full_name}
            if home_name and len(home_name) > 3:
                names_to_index.add(home_name)
            if slug_name and len(slug_name) > 3:
                names_to_index.add(slug_name)
            
            # Adiciona sobrenome/nome popular se tiver 2+ palavras (ex: "Ruud van Nistelrooy" -> "van Nistelrooy")
            parts = full_name.split()
            if len(parts) >= 2:
                if len(parts[-1]) >= 3:
                    names_to_index.add(parts[-1]) # ex: "Nistelrooy"
                if len(parts) >= 3 and parts[-2].lower() in ["van", "de", "da", "di", "del"]:
                    names_to_index.add(f"{parts[-2]} {parts[-1]}") # ex: "van Nistelrooy"

            club_clean = re.sub(r"\s*\(\d+\)$", "", club).strip() if club else "Sem Clube"
            norm_club = normalize_text(club_clean) or "sem clube"

            for name_variant in names_to_index:
                norm_name = normalize_text(name_variant)
                if not norm_name:
                    continue
                
                key = (norm_name, norm_club, pos_det)
                if key in seen:
                    continue
                seen.add(key)

                letra = norm_name[0].upper()
                items.append({
                    "pk": f"PLAYER#{norm_name}",
                    "sk": f"CLUB#{norm_club}#POS#{normalize_text(pos_det)}",
                    "type": "PLAYER",
                    "nome": full_name,
                    "apelido": name_variant,
                    "apelido_normalizado": norm_name,
                    "clube": club_clean,
                    "clube_normalizado": norm_club,
                    "posicao": pos_gen,
                    "posicao_detalhada": pos_det,
                    "letra_inicial": letra,
                    "pais": country
                })

            selected_players += 1
            # Limite confortável para importar milhares sem sobrecarregar o emulador de uma vez
            if selected_players >= 6000:
                break

    print(f"\nProcessamento concluído em {time.time() - t0:.1f}s!")
    print(f"Atletas selecionados do Transfermarkt: {selected_players}")
    print(f"Registros / Variações preparadas para o DynamoDB: {len(items)}")

    print("\nGravando no Amazon DynamoDB do AWS Emulator em lotes de 25...")
    t1 = time.time()
    written = batch_write(client, items)
    print(f"[SUCESSO] {written} registros inseridos com sucesso em {time.time() - t1:.1f}s!")

if __name__ == "__main__":
    import_transfermarkt_dataset()

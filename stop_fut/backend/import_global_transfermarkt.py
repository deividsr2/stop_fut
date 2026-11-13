"""
Importador Global de Dados do Futebol (Transfermarkt Datasets - David Cariboo).
Baixa os datasets públicos comprimidos (.csv.gz) diretamente do pipeline público:
- clubs.csv.gz (796 clubes mundiais, estádios, capacidades e técnicos)
- players.csv.gz (50.149 jogadores, posições detalhadas em inglês traduzidas para português)
- transfers.csv.gz (histórico completo de transferências de carreira entre clubes)

Insere no DynamoDB local do AWS Emulator em lotes (batch_write_item) de 25 itens.
"""

import os
import re
import csv
import gzip
import io
import time
import urllib.request
import unicodedata
import configparser
import boto3

EMULATOR_URL = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
HOME = os.path.expanduser("~")
EMULATOR_DIR = os.path.join(HOME, ".aws", "emulator", "9297")
TABLE_NAME = "stopfut_database"

R2_BASE_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"

POSITION_MAP = {
    "Goalkeeper": ("Goleiro", "Goleiro"),
    "Left-Back": ("Lateral", "Lateral Esquerdo"),
    "Right-Back": ("Lateral", "Lateral Direito"),
    "Centre-Back": ("Zagueiro", "Zagueiro"),
    "Defensive Midfield": ("Meio-campo", "Volante"),
    "Central Midfield": ("Meio-campo", "Meio-campo Central"),
    "Attacking Midfield": ("Meio-campo", "Meia-Atacante"),
    "Left Midfield": ("Meio-campo", "Meia Esquerda"),
    "Right Midfield": ("Meio-campo", "Meia Direita"),
    "Left Winger": ("Atacante", "Ponta Esquerda"),
    "Right Winger": ("Atacante", "Ponta Direita"),
    "Centre-Forward": ("Atacante", "Centroavante"),
    "Second Striker": ("Atacante", "Segundo Atacante"),
}

TOP_LEAGUES = {
    "BRA1": "Brasileirão Série A",
    "GB1": "Premier League (Inglaterra)",
    "ES1": "La Liga (Espanha)",
    "IT1": "Serie A (Itália)",
    "L1": "Bundesliga (Alemanha)",
    "FR1": "Ligue 1 (França)",
    "PO1": "Liga Portugal",
    "CL": "UEFA Champions League",
    "CLI": "Copa Libertadores"
}

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
    return text.strip().lower()

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
        aws_secret_access_key=secret
    )

def download_csv_gz(filename: str):
    url = f"{R2_BASE_URL}/{filename}"
    print(f"--> Baixando {filename} de {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (StopFut/1.0)"})
    with urllib.request.urlopen(req) as resp:
        gz = gzip.GzipFile(fileobj=io.BytesIO(resp.read()))
        return gz.read().decode("utf-8")

def flush_batch(client, items_buffer):
    if not items_buffer:
        return 0
    # Desduplica itens no buffer pela chave primária (pk, sk) para o DynamoDB
    unique_items = list({(it["pk"]["S"], it["sk"]["S"]): it for it in items_buffer}.values())
    total = 0
    for i in range(0, len(unique_items), 25):
        chunk = unique_items[i:i+25]
        req_items = [{ "PutRequest": { "Item": it } } for it in chunk]
        try:
            client.batch_write_item(RequestItems={TABLE_NAME: req_items})
            total += len(chunk)
        except Exception as e:
            print(f"Erro no batch_write: {e}")
    items_buffer.clear()
    return total

def run_import(max_players=8000):
    client = get_dynamo_client()
    total_written = 0
    buffer = []

    # 1. CLUBES e ESTÁDIOS
    print("\n--- 1. Importando Clubes Mundiais e Estádios ---")
    clubs_content = download_csv_gz("clubs.csv.gz")
    clubs_reader = csv.DictReader(io.StringIO(clubs_content))
    club_id_to_name = {}
    club_count = 0

    for row in clubs_reader:
        cid = row.get("club_id", "")
        cname = row.get("name", "").strip()
        stadium = row.get("stadium_name", "").strip()
        coach = row.get("coach_name", "").strip()
        comp = row.get("domestic_competition_id", "")

        if not cname:
            continue

        club_id_to_name[cid] = cname
        norm_name = normalize_text(cname)
        letra = norm_name[0].upper() if norm_name else "A"

        # Salva o Clube
        club_item = {
            "pk": {"S": f"CLUB#{norm_name}"},
            "sk": {"S": "INFO"},
            "type": {"S": "CLUB"},
            "nome": {"S": cname},
            "nome_normalizado": {"S": norm_name},
            "letra_inicial": {"S": letra},
            "competicao": {"S": comp}
        }
        if stadium:
            club_item["estadio"] = {"S": stadium}
        buffer.append(club_item)
        club_count += 1

        # Também cria registro de apelido simplificado (ex: "Palmeiras", "Flamengo")
        words = cname.split()
        for w in words:
            w_norm = normalize_text(w)
            if len(w_norm) >= 5 and w_norm not in ["esporte", "clube", "futebol", "sport", "sociedade", "atletico"]:
                buffer.append({
                    "pk": {"S": f"CLUB#{w_norm}"},
                    "sk": {"S": "INFO"},
                    "type": {"S": "CLUB"},
                    "nome": {"S": cname},
                    "nome_normalizado": {"S": w_norm},
                    "letra_inicial": {"S": w_norm[0].upper()},
                    "clube_oficial": {"S": cname}
                })

        # Salva o Estádio
        if stadium and len(stadium) > 3:
            norm_stad = normalize_text(stadium)
            buffer.append({
                "pk": {"S": f"STADIUM#{norm_stad}"},
                "sk": {"S": "INFO"},
                "type": {"S": "STADIUM"},
                "nome": {"S": stadium},
                "nome_normalizado": {"S": norm_stad},
                "letra_inicial": {"S": norm_stad[0].upper()},
                "clube": {"S": cname}
            })

        # Salva o Técnico
        if coach and len(coach) > 3:
            norm_coach = normalize_text(coach)
            buffer.append({
                "pk": {"S": f"COACH#{norm_coach}"},
                "sk": {"S": "INFO"},
                "type": {"S": "COACH"},
                "nome": {"S": coach},
                "nome_normalizado": {"S": norm_coach},
                "letra_inicial": {"S": norm_coach[0].upper()},
                "clube": {"S": cname}
            })

        if len(buffer) >= 250:
            total_written += flush_batch(client, buffer)

    total_written += flush_batch(client, buffer)
    print(f"Clubes e estádios importados. Total registros: {club_count}")

    # 2. HISTÓRICO DE TRANSFERÊNCIAS (Para saber clubes de passagem)
    print("\n--- 2. Mapeando Histórico de Transferências ---")
    trans_content = download_csv_gz("transfers.csv.gz")
    trans_reader = csv.DictReader(io.StringIO(trans_content))
    player_clubs = {}

    for row in trans_reader:
        pid = row.get("player_id", "")
        fc = row.get("from_club_name", "").strip()
        tc = row.get("to_club_name", "").strip()
        if not pid:
            continue
        if pid not in player_clubs:
            player_clubs[pid] = set()
        if fc: player_clubs[pid].add(fc)
        if tc: player_clubs[pid].add(tc)

    print(f"Histórico de transferências mapeado para {len(player_clubs)} jogadores.")

    # 3. JOGADORES (FILTRADOS POR RELEVÂNCIA: BRASIL + TOP LEAGUES + CRAQUES)
    print("\n--- 3. Importando Jogadores Globais e Brasileiros ---")
    players_content = download_csv_gz("players.csv.gz")
    players_reader = csv.DictReader(io.StringIO(players_content))
    imported_players = 0

    for row in players_reader:
        pid = row.get("player_id", "")
        pname = row.get("name", "").strip()
        fname = row.get("first_name", "").strip()
        lname = row.get("last_name", "").strip()
        sub_pos = row.get("sub_position", "").strip()
        pos_raw = row.get("position", "").strip()
        comp = row.get("current_club_domestic_competition_id", "")
        curr_club = row.get("current_club_name", "").strip()
        citizenship = row.get("country_of_citizenship", "").strip()
        peak_val = int(row.get("highest_market_value_in_eur") or 0)

        if not pname:
            continue

        # Filtro de relevância para o jogo
        is_relevant = (
            comp in TOP_LEAGUES or
            citizenship == "Brazil" or
            peak_val >= 1000000 or
            "brazil" in citizenship.lower()
        )
        if not is_relevant:
            continue

        # Mapeia posições para português
        pos_tuple = POSITION_MAP.get(sub_pos, (pos_raw or "Jogador", sub_pos or pos_raw or "Atleta"))
        pos_gen, pos_det = pos_tuple

        norm_full = normalize_text(pname)
        if not norm_full:
            continue
        letra_full = norm_full[0].upper()

        # Reúne todos os clubes que o jogador defendeu
        all_clubs = set(player_clubs.get(pid, []))
        if curr_club:
            all_clubs.add(curr_club)
        clubs_str = ", ".join(list(all_clubs)[:4]) if all_clubs else curr_club

        # 1. Registro principal com nome completo
        item_full = {
            "pk": {"S": f"PLAYER#{norm_full}"},
            "sk": {"S": f"INFO#{pid}"},
            "type": {"S": "PLAYER"},
            "nome": {"S": pname},
            "apelido": {"S": pname},
            "apelido_normalizado": {"S": norm_full},
            "posicao": {"S": pos_gen},
            "posicao_detalhada": {"S": pos_det},
            "letra_inicial": {"S": letra_full},
            "clube": {"S": clubs_str or "Internacional"},
            "clube_normalizado": {"S": normalize_text(curr_club or "internacional")},
            "pais": {"S": citizenship}
        }
        buffer.append(item_full)

        # 2. Vínculo por clube individual para categorias do tipo "Lateral do Palmeiras"
        for cl in all_clubs:
            norm_c = normalize_text(cl)
            if norm_c and len(norm_c) >= 3:
                buffer.append({
                    "pk": {"S": f"PLAYER#{norm_full}"},
                    "sk": {"S": f"CLUB#{norm_c}"},
                    "type": {"S": "PLAYER"},
                    "nome": {"S": pname},
                    "posicao": {"S": pos_gen},
                    "posicao_detalhada": {"S": pos_det},
                    "clube": {"S": cl},
                    "clube_normalizado": {"S": norm_c},
                    "letra_inicial": {"S": letra_full}
                })

        # 3. Registro por Sobrenome se for relevante (ex: Klose, Neuer, Buffon)
        if lname and len(lname) >= 3:
            norm_last = normalize_text(lname)
            if norm_last != norm_full and len(norm_last) >= 3:
                buffer.append({
                    "pk": {"S": f"PLAYER#{norm_last}"},
                    "sk": {"S": f"INFO#{pid}"},
                    "type": {"S": "PLAYER"},
                    "nome": {"S": pname},
                    "apelido": {"S": lname},
                    "apelido_normalizado": {"S": norm_last},
                    "posicao": {"S": pos_gen},
                    "posicao_detalhada": {"S": pos_det},
                    "letra_inicial": {"S": norm_last[0].upper()},
                    "clube": {"S": clubs_str or "Internacional"},
                    "clube_normalizado": {"S": normalize_text(curr_club or "internacional")}
                })

        imported_players += 1
        if len(buffer) >= 250:
            total_written += flush_batch(client, buffer)

        if imported_players >= max_players:
            break

    total_written += flush_batch(client, buffer)
    print(f"Jogadores importados: {imported_players}")
    print(f"Total geral de novos registros gravados no DynamoDB: {total_written}")

if __name__ == "__main__":
    t0 = time.time()
    print("Iniciando importação dos datasets Transfermarkt...")
    run_import(max_players=4000)
    print(f"Tempo total: {time.time() - t0:.2f}s")

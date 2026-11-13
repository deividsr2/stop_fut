"""
Script de Carga e Construção da Base de Dados do StopFut no DynamoDB.
Carrega jogadores, clubes, posições detalhadas, estádios e técnicos
no AWS Emulator local.
"""

import os
import sys
import zipfile
import csv
import io
import re
import unicodedata
import configparser
import urllib.request
import boto3
from botocore.config import Config

EMULATOR_URL = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
HOME = os.path.expanduser("~")
EMULATOR_DIR = os.path.join(HOME, ".aws", "emulator", "9297")
TABLE_NAME = "stopfut_database"

def normalize_text(text: str) -> str:
    """Remove acentos, caracteres especiais e converte para minúsculas."""
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
        aws_secret_access_key=secret,
        config=Config(retries={"max_attempts": 3, "mode": "standard"})
    )

def ensure_table(client):
    tables = client.list_tables().get("TableNames", [])
    if TABLE_NAME not in tables:
        print(f"Criando tabela '{TABLE_NAME}' no DynamoDB...")
        client.create_table(
            TableName=TABLE_NAME,
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
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print("Tabela criada e ativa!")
    else:
        print(f"Tabela '{TABLE_NAME}' já existe.")

def batch_write(client, items):
    """Grava itens no DynamoDB em lotes de até 25."""
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

# Laterais específicos (Esquerdo e Direito) com histórico dos principais clubes brasileiros
LATERAL_ESPECIFICO = {
    # Flamengo
    ("flamengo", "rene"): ("Lateral", "Lateral Esquerdo", "2017-2022"),
    ("flamengo", "ramon"): ("Lateral", "Lateral Esquerdo", "2020-2022"),
    ("flamengo", "reinaldo"): ("Lateral", "Lateral Esquerdo", "2001-2003"),
    ("flamengo", "ayrton lucas"): ("Lateral", "Lateral Esquerdo", "2022-2024"),
    ("flamengo", "filipe luis"): ("Lateral", "Lateral Esquerdo", "2019-2023"),
    ("flamengo", "matias vina"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("flamengo", "vina"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("flamengo", "alex sandro"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("flamengo", "jorge"): ("Lateral", "Lateral Esquerdo", "2014-2017"),
    ("flamengo", "juan"): ("Lateral", "Lateral Esquerdo", "2006-2010"),
    ("flamengo", "athirson"): ("Lateral", "Lateral Esquerdo", "1996-2004"),
    ("flamengo", "junior"): ("Lateral", "Lateral Esquerdo", "1974-1993"),
    ("flamengo", "andre santos"): ("Lateral", "Lateral Esquerdo", "2013-2014"),
    ("flamengo", "trauco"): ("Lateral", "Lateral Esquerdo", "2017-2019"),
    ("flamengo", "armero"): ("Lateral", "Lateral Esquerdo", "2015"),
    ("flamengo", "rodinei"): ("Lateral", "Lateral Direito", "2016-2022"),
    ("flamengo", "rafinha"): ("Lateral", "Lateral Direito", "2019-2020"),
    ("flamengo", "guillermo varela"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("flamengo", "varela"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("flamengo", "wesley"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("flamengo", "matheuzinho"): ("Lateral", "Lateral Direito", "2020-2023"),
    ("flamengo", "matheus franca"): ("Lateral", "Lateral Direito", "2020-2023"),
    ("flamengo", "isla"): ("Lateral", "Lateral Direito", "2020-2022"),
    ("flamengo", "para"): ("Lateral", "Lateral Direito", "2015-2019"),
    ("flamengo", "leo moura"): ("Lateral", "Lateral Direito", "2005-2014"),
    ("flamengo", "leonardo moura"): ("Lateral", "Lateral Direito", "2005-2014"),

    # Palmeiras
    ("palmeiras", "piquerez"): ("Lateral", "Lateral Esquerdo", "2021-2024"),
    ("palmeiras", "joaquin piquerez"): ("Lateral", "Lateral Esquerdo", "2021-2024"),
    ("palmeiras", "caio paulista"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("palmeiras", "vanderlan"): ("Lateral", "Lateral Esquerdo", "2022-2024"),
    ("palmeiras", "matias vina"): ("Lateral", "Lateral Esquerdo", "2020-2021"),
    ("palmeiras", "victor luis"): ("Lateral", "Lateral Esquerdo", "2014-2021"),
    ("palmeiras", "diogo barbosa"): ("Lateral", "Lateral Esquerdo", "2018-2020"),
    ("palmeiras", "ze roberto"): ("Lateral", "Lateral Esquerdo", "2015-2017"),
    ("palmeiras", "egidio"): ("Lateral", "Lateral Esquerdo", "2015-2017"),
    ("palmeiras", "roberto carlos"): ("Lateral", "Lateral Esquerdo", "1993-1995"),
    ("palmeiras", "marcos rocha"): ("Lateral", "Lateral Direito", "2018-2024"),
    ("palmeiras", "mayke"): ("Lateral", "Lateral Direito", "2017-2024"),
    ("palmeiras", "agustin giay"): ("Lateral", "Lateral Direito", "2024"),
    ("palmeiras", "garcia"): ("Lateral", "Lateral Direito", "2021-2024"),
    ("palmeiras", "arce"): ("Lateral", "Lateral Direito", "1998-2002"),
    ("palmeiras", "cafu"): ("Lateral", "Lateral Direito", "1995-1997"),

    # São Paulo
    ("sao paulo", "welington"): ("Lateral", "Lateral Esquerdo", "2020-2024"),
    ("sao paulo", "reinaldo"): ("Lateral", "Lateral Esquerdo", "2013-2022"),
    ("sao paulo", "jamal lewis"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("sao paulo", "caio paulista"): ("Lateral", "Lateral Esquerdo", "2023"),
    ("sao paulo", "junior tavares"): ("Lateral", "Lateral Esquerdo", "2017-2019"),
    ("sao paulo", "edimar"): ("Lateral", "Lateral Esquerdo", "2017-2018"),
    ("sao paulo", "carlinhos"): ("Lateral", "Lateral Esquerdo", "2015-2016"),
    ("sao paulo", "cortez"): ("Lateral", "Lateral Esquerdo", "2012-2013"),
    ("sao paulo", "juan"): ("Lateral", "Lateral Esquerdo", "2011-2012"),
    ("sao paulo", "richarlyson"): ("Lateral", "Lateral Esquerdo", "2005-2010"),
    ("sao paulo", "serginho"): ("Lateral", "Lateral Esquerdo", "1996-1999"),
    ("sao paulo", "rafinha"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("sao paulo", "igor vinicius"): ("Lateral", "Lateral Direito", "2019-2024"),
    ("sao paulo", "moreira"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("sao paulo", "dani alves"): ("Lateral", "Lateral Direito", "2019-2021"),
    ("sao paulo", "daniel alves"): ("Lateral", "Lateral Direito", "2019-2021"),
    ("sao paulo", "cicinho"): ("Lateral", "Lateral Direito", "2004-2005"),
    ("sao paulo", "ilsinho"): ("Lateral", "Lateral Direito", "2006-2007"),
    ("sao paulo", "cafu"): ("Lateral", "Lateral Direito", "1989-1994"),

    # Corinthians
    ("corinthians", "hugo"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("corinthians", "matheus bidu"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("corinthians", "fabio santos"): ("Lateral", "Lateral Esquerdo", "2011-2023"),
    ("corinthians", "lucas piton"): ("Lateral", "Lateral Esquerdo", "2020-2022"),
    ("corinthians", "sidcley"): ("Lateral", "Lateral Esquerdo", "2018-2020"),
    ("corinthians", "danilo avelar"): ("Lateral", "Lateral Esquerdo", "2018-2019"),
    ("corinthians", "guilherme arana"): ("Lateral", "Lateral Esquerdo", "2015-2017"),
    ("corinthians", "uendel"): ("Lateral", "Lateral Esquerdo", "2014-2016"),
    ("corinthians", "roberto carlos"): ("Lateral", "Lateral Esquerdo", "2010-2011"),
    ("corinthians", "andre santos"): ("Lateral", "Lateral Esquerdo", "2008-2009"),
    ("corinthians", "kleber"): ("Lateral", "Lateral Esquerdo", "1998-2003"),
    ("corinthians", "fagner"): ("Lateral", "Lateral Direito", "2014-2024"),
    ("corinthians", "matheuzinho"): ("Lateral", "Lateral Direito", "2024"),
    ("corinthians", "matheus franca"): ("Lateral", "Lateral Direito", "2024"),
    ("corinthians", "rafael ramos"): ("Lateral", "Lateral Direito", "2022-2023"),
    ("corinthians", "michel macedo"): ("Lateral", "Lateral Direito", "2019-2021"),
    ("corinthians", "alessandro"): ("Lateral", "Lateral Direito", "2008-2013"),
    ("corinthians", "ze maria"): ("Lateral", "Lateral Direito", "1970-1983"),

    # Vasco
    ("vasco", "lucas piton"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("vasco", "victor luis"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("vasco", "paulo victor"): ("Lateral", "Lateral Esquerdo", "2022-2023"),
    ("vasco", "riquelme"): ("Lateral", "Lateral Esquerdo", "2021-2023"),
    ("vasco", "henrique"): ("Lateral", "Lateral Esquerdo", "2013-2021"),
    ("vasco", "ramon"): ("Lateral", "Lateral Esquerdo", "2009-2019"),
    ("vasco", "felipe"): ("Lateral", "Lateral Esquerdo", "1996-2002"),
    ("vasco", "paulo henrique"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("vasco", "pumita rodriguez"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("vasco", "rodriguez"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("vasco", "leo matos"): ("Lateral", "Lateral Direito", "2020-2022"),
    ("vasco", "yago pikachu"): ("Lateral", "Lateral Direito", "2016-2021"),
    ("vasco", "madson"): ("Lateral", "Lateral Direito", "2015-2017"),
    ("vasco", "fagner"): ("Lateral", "Lateral Direito", "2009-2013"),

    # Fluminense
    ("fluminense", "marcelo"): ("Lateral", "Lateral Esquerdo", "2005-2024"),
    ("fluminense", "diogo barbosa"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("fluminense", "gabriel fontes"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("fluminense", "danilo barcelos"): ("Lateral", "Lateral Esquerdo", "2020-2022"),
    ("fluminense", "egidio"): ("Lateral", "Lateral Esquerdo", "2020-2021"),
    ("fluminense", "caio henrique"): ("Lateral", "Lateral Esquerdo", "2019"),
    ("fluminense", "ayrton lucas"): ("Lateral", "Lateral Esquerdo", "2018"),
    ("fluminense", "carlinhos"): ("Lateral", "Lateral Esquerdo", "2010-2014"),
    ("fluminense", "branco"): ("Lateral", "Lateral Esquerdo", "1981-1986"),
    ("fluminense", "samuel xavier"): ("Lateral", "Lateral Direito", "2021-2024"),
    ("fluminense", "guga"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("fluminense", "calegari"): ("Lateral", "Lateral Direito", "2020-2023"),
    ("fluminense", "gilberto"): ("Lateral", "Lateral Direito", "2018-2020"),
    ("fluminense", "mariano"): ("Lateral", "Lateral Direito", "2009-2011"),

    # Grêmio
    ("gremio", "reinaldo"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("gremio", "mayk"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("gremio", "cuiabano"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("gremio", "diogo barbosa"): ("Lateral", "Lateral Esquerdo", "2020-2023"),
    ("gremio", "cortez"): ("Lateral", "Lateral Esquerdo", "2017-2021"),
    ("gremio", "bruno cortez"): ("Lateral", "Lateral Esquerdo", "2017-2021"),
    ("gremio", "marcelo oliveira"): ("Lateral", "Lateral Esquerdo", "2015-2020"),
    ("gremio", "alex telles"): ("Lateral", "Lateral Esquerdo", "2013"),
    ("gremio", "joao pedro"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("gremio", "fabio"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("gremio", "vanderson"): ("Lateral", "Lateral Direito", "2020-2021"),
    ("gremio", "victor ferraz"): ("Lateral", "Lateral Direito", "2020-2021"),
    ("gremio", "leonardo gomes"): ("Lateral", "Lateral Direito", "2017-2022"),
    ("gremio", "edilson"): ("Lateral", "Lateral Direito", "2016-2022"),
    ("gremio", "leo moura"): ("Lateral", "Lateral Direito", "2017-2019"),

    # Internacional
    ("internacional", "bernabei"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("internacional", "alexandro bernabei"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("internacional", "rene"): ("Lateral", "Lateral Esquerdo", "2022-2024"),
    ("internacional", "moises"): ("Lateral", "Lateral Esquerdo", "2020-2022"),
    ("internacional", "uendel"): ("Lateral", "Lateral Esquerdo", "2017-2021"),
    ("internacional", "iago"): ("Lateral", "Lateral Esquerdo", "2017-2019"),
    ("internacional", "geferson"): ("Lateral", "Lateral Esquerdo", "2015-2017"),
    ("internacional", "fabricio"): ("Lateral", "Lateral Esquerdo", "2011-2015"),
    ("internacional", "kleber"): ("Lateral", "Lateral Esquerdo", "2009-2013"),
    ("internacional", "bustos"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("internacional", "fabricio bustos"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("internacional", "bruno gomes"): ("Lateral", "Lateral Direito", "2024"),
    ("internacional", "hugo mallo"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("internacional", "rodinei"): ("Lateral", "Lateral Direito", "2020-2021"),
    ("internacional", "heitor"): ("Lateral", "Lateral Direito", "2019-2022"),
    ("internacional", "zeca"): ("Lateral", "Lateral Direito", "2018-2020"),
    ("internacional", "william"): ("Lateral", "Lateral Direito", "2015-2017"),

    # Atlético-MG
    ("atletico-mg", "guilherme arana"): ("Lateral", "Lateral Esquerdo", "2020-2024"),
    ("atletico-mg", "arana"): ("Lateral", "Lateral Esquerdo", "2020-2024"),
    ("atletico-mg", "rubens"): ("Lateral", "Lateral Esquerdo", "2022-2024"),
    ("atletico-mg", "dodo"): ("Lateral", "Lateral Esquerdo", "2021-2023"),
    ("atletico-mg", "fabio santos"): ("Lateral", "Lateral Esquerdo", "2016-2020"),
    ("atletico-mg", "douglas santos"): ("Lateral", "Lateral Esquerdo", "2014-2016"),
    ("atletico-mg", "renzo saravia"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("atletico-mg", "saravia"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("atletico-mg", "mariano"): ("Lateral", "Lateral Direito", "2020-2024"),
    ("atletico-mg", "guga"): ("Lateral", "Lateral Direito", "2019-2022"),
    ("atletico-mg", "patric"): ("Lateral", "Lateral Direito", "2011-2020"),
    ("atletico-mg", "marcos rocha"): ("Lateral", "Lateral Direito", "2012-2017"),

    # Cruzeiro
    ("cruzeiro", "marlon"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("cruzeiro", "kaiki"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("cruzeiro", "matheus bidu"): ("Lateral", "Lateral Esquerdo", "2022"),
    ("cruzeiro", "egidio"): ("Lateral", "Lateral Esquerdo", "2013-2019"),
    ("cruzeiro", "diogo barbosa"): ("Lateral", "Lateral Esquerdo", "2017"),
    ("cruzeiro", "sorin"): ("Lateral", "Lateral Esquerdo", "2000-2009"),
    ("cruzeiro", "juan pablo sorin"): ("Lateral", "Lateral Esquerdo", "2000-2009"),
    ("cruzeiro", "william"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("cruzeiro", "helibelton palacios"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("cruzeiro", "palacios"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("cruzeiro", "wesley gasolina"): ("Lateral", "Lateral Direito", "2022-2024"),
    ("cruzeiro", "orejuela"): ("Lateral", "Lateral Direito", "2019-2020"),
    ("cruzeiro", "edilson"): ("Lateral", "Lateral Direito", "2018-2020"),
    ("cruzeiro", "mayke"): ("Lateral", "Lateral Direito", "2013-2017"),
    ("cruzeiro", "ceara"): ("Lateral", "Lateral Direito", "2012-2015"),

    # Botafogo
    ("botafogo", "alex telles"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("botafogo", "cuiabano"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("botafogo", "marcal"): ("Lateral", "Lateral Esquerdo", "2022-2024"),
    ("botafogo", "fernando marcal"): ("Lateral", "Lateral Esquerdo", "2022-2024"),
    ("botafogo", "hugo"): ("Lateral", "Lateral Esquerdo", "2021-2024"),
    ("botafogo", "victor luis"): ("Lateral", "Lateral Esquerdo", "2016-2020"),
    ("botafogo", "nilton santos"): ("Lateral", "Lateral Esquerdo", "1948-1964"),
    ("botafogo", "vitinho"): ("Lateral", "Lateral Direito", "2024"),
    ("botafogo", "mateo ponte"): ("Lateral", "Lateral Direito", "2023-2024"),
    ("botafogo", "damian suarez"): ("Lateral", "Lateral Direito", "2024"),
    ("botafogo", "rafael"): ("Lateral", "Lateral Direito", "2021-2024"),
    ("botafogo", "di placido"): ("Lateral", "Lateral Direito", "2023"),
    ("botafogo", "saravia"): ("Lateral", "Lateral Direito", "2022"),
    ("botafogo", "marcinho"): ("Lateral", "Lateral Direito", "2016-2020"),

    # Santos
    ("santos", "gonzalo escobar"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("santos", "escobar"): ("Lateral", "Lateral Esquerdo", "2024"),
    ("santos", "kevyson"): ("Lateral", "Lateral Esquerdo", "2023-2024"),
    ("santos", "felipe jonatan"): ("Lateral", "Lateral Esquerdo", "2019-2024"),
    ("santos", "lucas pires"): ("Lateral", "Lateral Esquerdo", "2022-2023"),
    ("santos", "zeca"): ("Lateral", "Lateral Esquerdo", "2014-2017"),
    ("santos", "dodo"): ("Lateral", "Lateral Esquerdo", "2018-2023"),
    ("santos", "leo"): ("Lateral", "Lateral Esquerdo", "2000-2014"),
    ("santos", "aderlan"): ("Lateral", "Lateral Direito", "2024"),
    ("santos", "jp chermont"): ("Lateral", "Lateral Direito", "2024"),
    ("santos", "hayner"): ("Lateral", "Lateral Direito", "2024"),
    ("santos", "nathan"): ("Lateral", "Lateral Direito", "2022-2023"),
    ("santos", "madson"): ("Lateral", "Lateral Direito", "2020-2022"),
    ("santos", "para"): ("Lateral", "Lateral Direito", "2008-2021"),
    ("santos", "victor ferraz"): ("Lateral", "Lateral Direito", "2014-2019"),
    ("santos", "danilo"): ("Lateral", "Lateral Direito", "2010-2011"),
    ("santos", "carlos alberto"): ("Lateral", "Lateral Direito", "1965-1974")
}

POS_MAP_CARTOLA = {
    "1": ("Goleiro", "Goleiro"),
    "2": ("Lateral", "Lateral"),
    "3": ("Zagueiro", "Zagueiro"),
    "4": ("Meia", "Meio-campo"),
    "5": ("Atacante", "Atacante"),
    "6": ("Tecnico", "Tecnico")
}

def load_data():
    items = []
    seen_keys = set()

    def add_item(it):
        key = (it["pk"], it["sk"])
        if key not in seen_keys:
            seen_keys.add(key)
            items.append(it)

    # 1. Carrega dados enriquecidos de laterais
    for (clube_norm, apelido_norm), (pos_gen, pos_det, anos) in LATERAL_ESPECIFICO.items():
        letra = apelido_norm[0].upper()
        # Chave direta por jogador
        add_item({
            "pk": f"PLAYER#{apelido_norm}",
            "sk": f"CLUB#{clube_norm}#POS#{normalize_text(pos_det)}",
            "type": "PLAYER",
            "apelido": apelido_norm.title(),
            "apelido_normalizado": apelido_norm,
            "clube": clube_norm.title(),
            "clube_normalizado": clube_norm,
            "posicao": pos_gen,
            "posicao_detalhada": pos_det,
            "letra_inicial": letra,
            "anos": anos
        })
        # Chave indexada por clube + posição + letra para busca instantânea!
        add_item({
            "pk": f"SEARCH#{clube_norm}#{normalize_text(pos_det)}#{letra}",
            "sk": f"PLAYER#{apelido_norm}",
            "type": "INDEX",
            "apelido": apelido_norm.title(),
            "apelido_normalizado": apelido_norm,
            "clube": clube_norm.title(),
            "posicao_detalhada": pos_det,
            "anos": anos
        })

    # 2. Carrega dados do ZIP campeonato brasileiro (Cartões, Gols, Partidas)
    zip_path = "data/archive.zip"
    if os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, "r") as z:
            # Arenas e Técnicos
            if "campeonato-brasileiro-full.csv" in z.namelist():
                with z.open("campeonato-brasileiro-full.csv") as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="ignore"))
                    for r in reader:
                        arena = r.get("arena", "").strip().replace("\xa0", "")
                        if arena and len(arena) > 2:
                            norm_arena = normalize_text(arena)
                            if norm_arena:
                                add_item({
                                    "pk": f"STADIUM#{norm_arena}",
                                    "sk": "INFO",
                                    "type": "STADIUM",
                                    "nome": arena,
                                    "nome_normalizado": norm_arena,
                                    "letra_inicial": norm_arena[0].upper()
                                })
                        for tc, c in [(r.get("tecnico_mandante", ""), r.get("mandante", "")), (r.get("tecnico_visitante", ""), r.get("visitante", ""))]:
                            tc = tc.strip()
                            if tc and len(tc) > 3:
                                norm_tc = normalize_text(tc)
                                norm_c = normalize_text(c)
                                if norm_tc:
                                    add_item({
                                        "pk": f"COACH#{norm_tc}",
                                        "sk": f"CLUB#{norm_c}",
                                        "type": "COACH",
                                        "nome": tc,
                                        "nome_normalizado": norm_tc,
                                        "clube": c,
                                        "clube_normalizado": norm_c,
                                        "letra_inicial": norm_tc[0].upper()
                                    })
                        for cl in [r.get("mandante", ""), r.get("visitante", "")]:
                            cl = cl.strip()
                            if cl and len(cl) > 2:
                                norm_cl = normalize_text(cl)
                                if norm_cl:
                                    add_item({
                                        "pk": f"CLUB#{norm_cl}",
                                        "sk": "INFO",
                                        "type": "CLUB",
                                        "nome": cl,
                                        "nome_normalizado": norm_cl,
                                        "letra_inicial": norm_cl[0].upper()
                                    })

            # Cartões (jogadores históricos + posições gerais)
            if "campeonato-brasileiro-cartoes.csv" in z.namelist():
                with z.open("campeonato-brasileiro-cartoes.csv") as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="ignore"))
                    count = 0
                    for r in reader:
                        atleta = r.get("atleta", "").strip()
                        clube = r.get("clube", "").strip()
                        pos = r.get("posicao", "").strip() or "Jogador"
                        if atleta and clube:
                            norm_atleta = normalize_text(atleta)
                            norm_clube = normalize_text(clube)
                            if norm_atleta and norm_clube:
                                letra = norm_atleta[0].upper()
                                add_item({
                                    "pk": f"PLAYER#{norm_atleta}",
                                    "sk": f"CLUB#{norm_clube}#POS#{normalize_text(pos)}",
                                    "type": "PLAYER",
                                    "apelido": atleta,
                                    "apelido_normalizado": norm_atleta,
                                    "clube": clube,
                                    "clube_normalizado": norm_clube,
                                    "posicao": pos,
                                    "posicao_detalhada": pos,
                                    "letra_inicial": letra
                                })
                                count += 1
                                if count > 4000:  # Limite saudável para o emulador local
                                    break

    # 3. Carrega atletas adicionais do Cartola FC (2024 e 2023)
    cartola_urls = [
        "https://raw.githubusercontent.com/henriquepgomide/caRtola/master/data/01_raw/2024/rodada-1.csv",
        "https://raw.githubusercontent.com/henriquepgomide/caRtola/master/data/01_raw/2024/rodada-20.csv",
        "https://raw.githubusercontent.com/henriquepgomide/caRtola/master/data/01_raw/2023/rodada-1.csv"
    ]
    for url in cartola_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                reader = csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8", errors="ignore"))
                for row in reader:
                    apelido = row.get("atletas.apelido", "").strip()
                    nome = row.get("atletas.nome", "").strip()
                    clube = row.get("atletas.clube.id.full.name", "").strip()
                    pos_id = row.get("atletas.posicao_id", "").strip()
                    pos_gen, pos_det = POS_MAP_CARTOLA.get(pos_id, ("Jogador", "Jogador"))
                    
                    if apelido and clube:
                        norm_apelido = normalize_text(apelido)
                        norm_clube = normalize_text(clube)
                        if norm_apelido and norm_clube:
                            letra = norm_apelido[0].upper()
                            # Se for lateral, verifica se temos a especialização em LATERAL_ESPECIFICO
                            if pos_gen == "Lateral":
                                if (norm_clube, norm_apelido) in LATERAL_ESPECIFICO:
                                    _, pos_det, anos = LATERAL_ESPECIFICO[(norm_clube, norm_apelido)]
                                else:
                                    pos_det = "Lateral"

                            add_item({
                                "pk": f"PLAYER#{norm_apelido}",
                                "sk": f"CLUB#{norm_clube}#POS#{normalize_text(pos_det)}",
                                "type": "PLAYER",
                                "nome": nome,
                                "apelido": apelido,
                                "apelido_normalizado": norm_apelido,
                                "clube": clube,
                                "clube_normalizado": norm_clube,
                                "posicao": pos_gen,
                                "posicao_detalhada": pos_det,
                                "letra_inicial": letra
                            })
        except Exception as e:
            print(f"Aviso ao baixar Cartola FC ({url}): {e}")

    # 4. Clubes mundiais e brasileiros de destaque
    clubes_destaque = [
        "Flamengo", "Palmeiras", "Sao Paulo", "Corinthians", "Santos", "Fluminense",
        "Vasco da Gama", "Botafogo", "Gremio", "Internacional", "Cruzeiro", "Atletico Mineiro",
        "Bahia", "Fortaleza", "Athletico Paranaense", "Coritiba", "Goias", "Sport Recife",
        "Ceara", "Vitoria", "Juventude", "Cuiaba", "Red Bull Bragantino",
        "Real Madrid", "Barcelona", "Manchester City", "Liverpool", "Arsenal", "Chelsea",
        "Bayern de Munique", "Paris Saint-Germain", "Juventus", "Milan", "Inter de Milao",
        "Benfica", "Porto", "Sporting", "Boca Juniors", "River Plate"
    ]
    for c in clubes_destaque:
        nc = normalize_text(c)
        add_item({
            "pk": f"CLUB#{nc}",
            "sk": "INFO",
            "type": "CLUB",
            "nome": c,
            "nome_normalizado": nc,
            "letra_inicial": nc[0].upper()
        })

    # 5. Craques e jogadores lendários adicionais
    craques = [
        ("Pele", "Santos", "Atacante", "Atacante"),
        ("Zico", "Flamengo", "Meia", "Meio-campo"),
        ("Romario", "Flamengo", "Atacante", "Centroavante"),
        ("Romario", "Vasco da Gama", "Atacante", "Centroavante"),
        ("Ronaldo Fenomeno", "Corinthians", "Atacante", "Centroavante"),
        ("Ronaldo Fenomeno", "Cruzeiro", "Atacante", "Centroavante"),
        ("Ronaldinho Gaucho", "Flamengo", "Meia", "Meio-campo"),
        ("Ronaldinho Gaucho", "Atletico Mineiro", "Meia", "Meio-campo"),
        ("Ronaldinho Gaucho", "Gremio", "Atacante", "Ponta"),
        ("Neymar", "Santos", "Atacante", "Ponta Esquerda"),
        ("Kaka", "Sao Paulo", "Meia", "Meio-campo"),
        ("Rogério Ceni", "Sao Paulo", "Goleiro", "Goleiro"),
        ("Marcos", "Palmeiras", "Goleiro", "Goleiro"),
        ("Cassio", "Corinthians", "Goleiro", "Goleiro"),
        ("Cassio", "Cruzeiro", "Goleiro", "Goleiro"),
        ("Gabigol", "Flamengo", "Atacante", "Centroavante"),
        ("Gabigol", "Santos", "Atacante", "Centroavante"),
        ("Pedro", "Flamengo", "Atacante", "Centroavante"),
        ("Pedro", "Fluminense", "Atacante", "Centroavante"),
        ("Arrascaeta", "Flamengo", "Meia", "Meio-campo"),
        ("Arrascaeta", "Cruzeiro", "Meia", "Meio-campo"),
        ("Everton Ribeiro", "Flamengo", "Meia", "Meio-campo"),
        ("Everton Ribeiro", "Bahia", "Meia", "Meio-campo"),
        ("Everton Ribeiro", "Cruzeiro", "Meia", "Meio-campo"),
        ("Gerson", "Flamengo", "Meia", "Volante"),
        ("Gerson", "Fluminense", "Meia", "Meio-campo"),
        ("Bruno Henrique", "Flamengo", "Atacante", "Ponta"),
        ("Bruno Henrique", "Santos", "Atacante", "Ponta"),
        ("Calleri", "Sao Paulo", "Atacante", "Centroavante"),
        ("Lucas Moura", "Sao Paulo", "Atacante", "Ponta"),
        ("Veiga", "Palmeiras", "Meia", "Meio-campo"),
        ("Raphael Veiga", "Palmeiras", "Meia", "Meio-campo"),
        ("Dudu", "Palmeiras", "Atacante", "Ponta"),
        ("Hulk", "Atletico Mineiro", "Atacante", "Atacante"),
        ("Paulinho", "Atletico Mineiro", "Atacante", "Atacante"),
        ("Cano", "Fluminense", "Atacante", "Centroavante"),
        ("Cano", "Vasco da Gama", "Atacante", "Centroavante"),
        ("Ganso", "Fluminense", "Meia", "Meio-campo"),
        ("Ganso", "Santos", "Meia", "Meio-campo"),
        ("Ganso", "Sao Paulo", "Meia", "Meio-campo"),
        ("Payet", "Vasco da Gama", "Meia", "Meio-campo"),
        ("Vegetty", "Vasco da Gama", "Atacante", "Centroavante"),
        ("Pablo Vegetti", "Vasco da Gama", "Atacante", "Centroavante"),
        ("Suarez", "Gremio", "Atacante", "Centroavante"),
        ("Luis Suarez", "Gremio", "Atacante", "Centroavante"),
        ("Enner Valencia", "Internacional", "Atacante", "Centroavante"),
        ("Alan Patrick", "Internacional", "Meia", "Meio-campo"),
        ("Depay", "Corinthians", "Atacante", "Atacante"),
        ("Memphis Depay", "Corinthians", "Atacante", "Atacante"),
        ("Yuri Alberto", "Corinthians", "Atacante", "Centroavante"),
        ("Rodrigo Garro", "Corinthians", "Meia", "Meio-campo"),
        ("Garro", "Corinthians", "Meia", "Meio-campo"),
        ("Luiz Henrique", "Botafogo", "Atacante", "Ponta"),
        ("Igor Jesus", "Botafogo", "Atacante", "Centroavante"),
        ("Almada", "Botafogo", "Meia", "Meio-campo"),
        ("Thiago Silva", "Fluminense", "Zagueiro", "Zagueiro")
    ]
    for apelido, clube, pos_gen, pos_det in craques:
        na = normalize_text(apelido)
        nc = normalize_text(clube)
        letra = na[0].upper()
        add_item({
            "pk": f"PLAYER#{na}",
            "sk": f"CLUB#{nc}#POS#{normalize_text(pos_det)}",
            "type": "PLAYER",
            "apelido": apelido,
            "apelido_normalizado": na,
            "clube": clube,
            "clube_normalizado": nc,
            "posicao": pos_gen,
            "posicao_detalhada": pos_det,
            "letra_inicial": letra
        })

    return items

def main():
    print("=" * 60)
    print("   CONSTRUTOR DA BASE DE DADOS DO STOPFUT NO DYNAMODB")
    print("=" * 60)
    
    client = get_dynamo_client()
    ensure_table(client)
    
    print("\nColetando e normalizando dados de futebol...")
    items = load_data()
    print(f"Total de registros preparados: {len(items)}")
    
    print("\nGravando registros em lote no DynamoDB do AWS Emulator...")
    written = batch_write(client, items)
    print(f"[SUCESSO] {written} registros inseridos na tabela '{TABLE_NAME}'!")

if __name__ == "__main__":
    main()

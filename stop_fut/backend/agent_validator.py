"""
Agente Validador Inteligente do StopFut (O Árbitro da Adedonha com VAR 3.0).
Valida as respostas com tolerância inteligente a variações e apelidos:
- Nível 1: Consulta direta com mapeamento de apelidos e sinônimos no DynamoDB
- Nível 2: Busca fuzzy (similaridade fonética/ortográfica)
- Nível 3: Pesquisa em tempo real na Enciclopédia do Futebol (VAR Online)
  com auto-aprendizado (salva novos jogadores e clubes diretamente no DynamoDB local!)
"""

import os
import re
import json
import difflib
import unicodedata
import configparser
import urllib.request
import urllib.parse
import boto3

EMULATOR_URL = os.environ.get("AWS_ENDPOINT_URL", "https://127.0.0.1:9297")
HOME = os.path.expanduser("~")
EMULATOR_DIR = os.path.join(HOME, ".aws", "emulator", "9297")
TABLE_NAME = "stopfut_database"

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
    return text.strip().lower()

# Sinônimos e variações populares de nomes de clubes
CLUB_ALIASES = {
    "america mineiro": "america-mg",
    "america de minas": "america-mg",
    "coelho": "america-mg",
    "atletico mineiro": "atletico-mg",
    "atletico de minas": "atletico-mg",
    "galo": "atletico-mg",
    "athletico paranaense": "athletico-pr",
    "atletico paranaense": "athletico-pr",
    "furacao": "athletico-pr",
    "inter": "internacional",
    "inter de porto alegre": "internacional",
    "colorado": "internacional",
    "gremio": "gremio",
    "imortal": "gremio",
    "tricolor gaucho": "gremio",
    "sao paulo": "sao paulo",
    "spfc": "sao paulo",
    "tricolor paulista": "sao paulo",
    "corinthians": "corinthians",
    "timao": "corinthians",
    "coringao": "corinthians",
    "flamengo": "flamengo",
    "fla": "flamengo",
    "mengo": "flamengo",
    "mengao": "flamengo",
    "rubro-negro": "flamengo",
    "fluminense": "fluminense",
    "flu": "fluminense",
    "fluzão": "fluminense",
    "tricolor carioca": "fluminense",
    "botafogo": "botafogo",
    "fogao": "botafogo",
    "glorioso": "botafogo",
    "bota": "botafogo",
    "vasco": "vasco",
    "vasco da gama": "vasco",
    "gigante da colina": "vasco",
    "cruzeiro": "cruzeiro",
    "raposa": "cruzeiro",
    "cabuloso": "cruzeiro",
    "santos": "santos",
    "peixe": "santos",
    "palmeiras": "palmeiras",
    "verdao": "palmeiras",
    "alviverde": "palmeiras",
    "porco": "palmeiras",
    "bragantino": "red bull bragantino",
    "rb bragantino": "red bull bragantino",
    "real": "real madrid",
    "real madrid": "real madrid",
    "barca": "barcelona",
    "barcelona": "barcelona",
    "city": "manchester city",
    "united": "manchester united",
    "bayern": "bayern de munique",
    "psg": "paris saint-germain",
    "boca": "boca juniors",
    "river": "river plate"
}

# Sinônimos e apelidos populares de jogadores
PLAYER_ALIASES = {
    # Goleiros
    "grohe": "marcelo grohe",
    "marcelo grohe": "marcelo grohe",
    "buffon": "gianluigi buffon",
    "neuer": "manuel neuer",
    "courtois": "thibaut courtois",
    "casillas": "iker casillas",
    "kahn": "oliver kahn",
    "dida": "dida",
    "taffarel": "claudio taffarel",
    "cassio": "cassio ramos",
    "weverton": "weverton pereira da silva",
    "alisson": "alisson becker",
    "ederson": "ederson moraes",
    "rochet": "sergio rochet",
    "rossi": "agustin rossi",
    "bento": "bento krepski",
    "everson": "everson marques pires",
    "diego alves": "diego alves",
    "hugo souza": "hugo souza",
    "donnarumma": "gianluigi donnarumma",
    "ter stegen": "marc-andre ter stegen",
    "oblak": "jan oblak",
    "de gea": "david de gea",
    "martinez": "emiliano martinez",
    "dibu martinez": "emiliano martinez",
    "sommer": "yann sommer",
    "szczesny": "wojciech szczesny",

    # Laterais e Zagueiros
    "maldini": "paolo maldini",
    "cannavaro": "fabio cannavaro",
    "nesta": "alessandro nesta",
    "cafu": "cafu",
    "roberto carlos": "roberto carlos",
    "marcelo": "marcelo vieira",
    "filipe luis": "filipe luis",
    "dani alves": "daniel alves",
    "daniel alves": "daniel alves",
    "lahm": "philipp lahm",
    "sergio ramos": "sergio ramos",
    "ramos": "sergio ramos",
    "pique": "gerard pique",
    "puyol": "carles puyol",
    "van dijk": "virgil van dijk",
    "thiago silva": "thiago silva",
    "marquinhos": "marcos aoas correa",
    "david luiz": "david luiz",
    "ayrton lucas": "ayrton lucas",
    "piquerez": "joaquin piquerez",
    "wellington": "welington damascena",
    "reinaldo": "reinaldo manoel",
    "fagner": "fagner conserva lemos",
    "arana": "guilherme arana",
    "guilherme arana": "guilherme arana",
    "gustavo gomez": "gustavo gomez",
    "murilo": "murilo cerqueira",
    "leo pereira": "leo pereira",

    # Meias
    "modric": "luka modric",
    "kroos": "toni kroos",
    "zidane": "zinedine zidane",
    "pirlo": "andrea pirlo",
    "xavi": "xavi hernandez",
    "iniesta": "andres iniesta",
    "de bruyne": "kevin de bruyne",
    "kaka": "kaka",
    "ganso": "paulo henrique ganso",
    "arrascaeta": "giorgian de arrascaeta",
    "de arrascaeta": "giorgian de arrascaeta",
    "everton ribeiro": "everton ribeiro",
    "raphael veiga": "raphael veiga",
    "veiga": "raphael veiga",
    "gerson": "gerson santos",
    "bellingham": "jude bellingham",
    "oscar": "oscar emboaba",
    "oscar emboaba": "oscar emboaba",
    "socrates": "socrates brasileiro",
    "falcao": "paulo roberto falcao",
    "dunga": "dunga",
    "fred": "frederico chaves guedes",
    "pele": "edson arantes do nascimento",
    "garrincha": "manuel francisco dos santos",
    "zico": "arthur antunes coimbra",
    "tostao": "eduardo goncalves de andrade",
    "jairzinho": "jair ventura filho",
    "careca": "antonio de oliveira filho",
    "bebeto": "jose roberto gama de oliveira",
    "romario": "romario de souza faria",
    "rivaldo": "rivaldo vitor borba ferreira",

    # Atacantes
    "cr7": "cristiano ronaldo",
    "cristiano ronaldo": "cristiano ronaldo",
    "cristiano": "cristiano ronaldo",
    "messi": "lionel messi",
    "lionel messi": "lionel messi",
    "neymar": "neymar jr",
    "neymar jr": "neymar jr",
    "ronaldinho": "ronaldinho gaucho",
    "ronaldinho gaucho": "ronaldinho gaucho",
    "ronaldo": "ronaldo nazario",
    "ronaldo fenomeno": "ronaldo nazario",
    "fenomeno": "ronaldo nazario",
    "van nistelrooy": "ruud van nistelrooy",
    "ruud van nistelrooy": "ruud van nistelrooy",
    "suarez": "luis suarez",
    "luis suarez": "luis suarez",
    "lewandowski": "robert lewandowski",
    "benzema": "karim benzema",
    "haaland": "erling haaland",
    "mbappe": "kylian mbappe",
    "kane": "harry kane",
    "salah": "mohamed salah",
    "mane": "sadio mane",
    "gabigol": "gabriel barbosa",
    "pedro": "pedro guilherme",
    "hulk": "givanildo vieira de sousa",
    "calleri": "jonathan calleri",
    "cano": "german cano",
    "german cano": "german cano",
    "dudu": "eduardo pereira rodrigues",
    "rony": "ronielson da silva barbosa",
    "lucas moura": "lucas moura",
    "endrick": "endrick felipe",
    "estevao": "estevao willian",
    "vinicius jr": "vinicius junior",
    "vini jr": "vinicius junior",
    "rodrygo": "rodrygo silva de goes"
}

class FootballAgentValidator:
    def __init__(self):
        self.client = self._init_dynamo()
        self._cache_clubs = None

    def _init_dynamo(self):
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

    def validate_answer(self, letter: str, category_id: str, category_name: str, answer: str) -> dict:
        letter = letter.strip().upper()
        raw_ans = answer.strip()
        norm_ans = normalize_text(raw_ans)

        # 1. Resposta em branco
        if not norm_ans:
            return {
                "valid": False,
                "points": 0,
                "reason": "Resposta não informada.",
                "answer": ""
            }

        # 2. Validação de tamanho mínimo (impede letras soltas como 'g')
        if len(norm_ans) < 2:
            return {
                "valid": False,
                "points": 0,
                "reason": f"Resposta inválida ('{raw_ans}'). Digite o nome completo.",
                "answer": raw_ans
            }

        # 3. Validação da letra inicial
        initial = norm_ans[0].upper()
        if initial != letter:
            return {
                "valid": False,
                "points": 0,
                "reason": f"Não começa com a letra '{letter}' (começa com '{initial}').",
                "answer": raw_ans
            }

        # 4. Roteamento Inteligente por Categoria:
        # Linha Defensiva (Zagueiro ou Lateral)
        if category_id == "defesa" or "defensiva" in category_name.lower():
            return self._validate_player_by_sector(norm_ans, raw_ans, "defesa", letter)

        # Meiuca (Volante ou Meio-Campo)
        if category_id == "meiuca" or "meiuca" in category_name.lower():
            return self._validate_player_by_sector(norm_ans, raw_ans, "meiuca", letter)

        # Ataque (Centroavante, Ponta ou Segundo Atacante)
        if category_id == "ataque" or ("ataque" in category_name.lower() and " do " not in category_name.lower()):
            return self._validate_player_by_sector(norm_ans, raw_ans, "ataque", letter)

        # Volante de Qualquer Clube
        if category_id == "volante" or (category_name.lower().startswith("volante") and " do " not in category_name.lower()):
            return self._validate_player_by_position(norm_ans, raw_ans, "volante", letter)

        # Goleiro (Qualquer Clube)
        if category_id == "goleiro" or (category_name.lower().startswith("goleiro") and " do " not in category_name.lower()):
            return self._validate_player_by_position(norm_ans, raw_ans, "goleiro", letter)

        # Atacante / Goleador
        if category_id == "atacante" or (category_name.lower().startswith("atacante") and " do " not in category_name.lower()):
            return self._validate_player_by_position(norm_ans, raw_ans, "atacante", letter)

        # Clube / Time de Futebol
        if category_id == "clube" or (category_name.lower().startswith("clube") and " do " not in category_name.lower()):
            return self._validate_club(norm_ans, raw_ans, letter)

        # Estádio / Arena
        if category_id == "estadio" or category_name.lower().startswith("estadio") or category_name.lower().startswith("arena"):
            return self._validate_stadium(norm_ans, raw_ans, letter)

        # Técnico / Treinador
        if category_id == "tecnico" or category_name.lower().startswith("tecnico") or category_name.lower().startswith("treinador"):
            return self._validate_coach(norm_ans, raw_ans, letter)

        # Posição de Clube Específico (ex: "Lateral Esquerdo do São Paulo", "Volante do Corinthians", "Atacante do Flamengo")
        match = re.search(r"^(lateral(?:\s+esquerdo|\s+direito)?|goleiro|zagueiro|meia|volante|atacante|tecnico)\s+do\s+(.+)$", category_name.strip(), re.IGNORECASE)
        if match:
            target_pos = normalize_text(match.group(1))
            target_club = normalize_text(match.group(2))
            target_club = CLUB_ALIASES.get(target_club, target_club)
            return self._validate_player_club_position(norm_ans, raw_ans, target_club, target_pos, letter)

        # Categoria Genérica: Jogador / Craque
        return self._validate_generic_player(norm_ans, raw_ans, letter)

    # -------------------------------------------------------------
    # VALIDAÇÃO DE JOGADOR POR SETOR (Linha Defensiva, Meiuca, Ataque)
    # -------------------------------------------------------------
    def _validate_player_by_sector(self, norm_ans: str, raw_ans: str, sector: str, letter: str) -> dict:
        mapped_ans = PLAYER_ALIASES.get(norm_ans, norm_ans)

        SECTORS = {
            "defesa": {
                "name": "Linha Defensiva",
                "keywords": {"zagueiro", "lateral", "lateral esquerdo", "lateral direito", "centre-back", "left-back", "right-back", "defensor", "libero", "beque", "defender"},
                "wiki_words": ["zagueiro", "lateral", "defensor", "defesa"]
            },
            "meiuca": {
                "name": "Meiuca",
                "keywords": {"meio-campo", "volante", "meia", "meia-atacante", "meia central", "meia esquerda", "meia direita", "defensive midfield", "central midfield", "attacking midfield", "left midfield", "right midfield", "meio-campista", "midfield", "midfielder"},
                "wiki_words": ["meio-campo", "meio-campista", "volante", "meia", "armador"]
            },
            "ataque": {
                "name": "Ataque",
                "keywords": {"atacante", "centroavante", "ponta", "ponta esquerda", "ponta direita", "segundo atacante", "centre-forward", "second striker", "left winger", "right winger", "forward", "striker", "goleador", "artilheiro", "attack"},
                "wiki_words": ["atacante", "centroavante", "ponta", "goleador", "artilheiro"]
            }
        }

        sector_cfg = SECTORS.get(sector, SECTORS["meiuca"])
        sector_name = sector_cfg["name"]
        keywords = sector_cfg["keywords"]

        # Nível 1: Consulta direta no DynamoDB
        try:
            items = []
            for query_name in {norm_ans, mapped_ans}:
                res = self.client.query(
                    TableName=TABLE_NAME,
                    KeyConditionExpression="pk = :pk",
                    ExpressionAttributeValues={":pk": {"S": f"PLAYER#{query_name}"}}
                )
                items.extend(res.get("Items", []))

            # Nível 2: Busca fuzzy se não achou direto
            if not items:
                scan_res = self.client.scan(
                    TableName=TABLE_NAME,
                    FilterExpression="#tp = :t and letra_inicial = :l",
                    ExpressionAttributeNames={"#tp": "type"},
                    ExpressionAttributeValues={":t": {"S": "PLAYER"}, ":l": {"S": letter}},
                    Limit=150
                )
                for it in scan_res.get("Items", []):
                    db_name = it.get("apelido_normalizado", {}).get("S", "")
                    if difflib.SequenceMatcher(None, norm_ans, db_name).ratio() >= 0.82 or difflib.SequenceMatcher(None, mapped_ans, db_name).ratio() >= 0.82:
                        items.append(it)

            if items:
                for it in items:
                    pos_gen = normalize_text(it.get("posicao", {}).get("S", ""))
                    pos_det = normalize_text(it.get("posicao_detalhada", {}).get("S", ""))
                    nome = it.get("nome", {}).get("S", it.get("apelido", {}).get("S", raw_ans))
                    clube = it.get("clube", {}).get("S", "")
                    passagem = f" (passagens por {clube})" if clube else ""

                    if any(k in pos_gen or k in pos_det or pos_gen in k or pos_det in k for k in keywords):
                        return {
                            "valid": True,
                            "points": 10,
                            "reason": f"Golaço! {nome} ({pos_det.title()}{passagem}) comanda a {sector_name}!",
                            "answer": raw_ans
                        }

                pos_real = items[0].get("posicao_detalhada", {}).get("S", items[0].get("posicao", {}).get("S", "outra posição"))
                nome = items[0].get("nome", {}).get("S", raw_ans)
                return {
                    "valid": False,
                    "points": 0,
                    "reason": f"Falta tática! {nome} jogava como {pos_real}, e não na {sector_name}.",
                    "answer": raw_ans
                }
        except Exception as e:
            print(f"Erro DynamoDB setor {sector}:", e)

        # Nível 3: VAR Online
        ext = None
        for cand in [raw_ans, mapped_ans, f"{mapped_ans} futebol"]:
            ext = self._search_external_soccer(cand)
            if ext and (ext["is_player"] or "futebolista" in ext["description"].lower() or "futebol" in ext["extract"].lower()):
                break

        if ext and (ext["is_player"] or "futebolista" in ext["description"].lower() or "futebol" in ext["extract"].lower()):
            full = f"{ext['description']} {ext['extract']}".lower()
            is_match = any(w in full for w in sector_cfg["wiki_words"])
            if is_match:
                save_payload = {
                    "nome": ext["title"],
                    "apelido": ext["title"],
                    "apelido_normalizado": norm_ans,
                    "posicao": ext.get("position", sector_name),
                    "posicao_detalhada": ext.get("position", sector_name),
                    "letra_inicial": letter,
                    "clube": "Futebol Internacional"
                }
                self._save_to_dynamo(f"PLAYER#{norm_ans}", "INFO#GLOBAL", "PLAYER", save_payload)
                if mapped_ans != norm_ans:
                    self._save_to_dynamo(f"PLAYER#{mapped_ans}", "INFO#GLOBAL", "PLAYER", save_payload)
                return {
                    "valid": True,
                    "points": 10,
                    "reason": f"Golaço confirmado pelo VAR! {ext['title']} é um jogador de {sector_name} ({ext['description']}).",
                    "answer": raw_ans
                }
            else:
                return {
                    "valid": False,
                    "points": 0,
                    "reason": f"Setor incorreto! {ext['title']} atuava como {ext.get('position', 'outra posição')}, não na {sector_name}.",
                    "answer": raw_ans
                }

        return {
            "valid": False,
            "points": 0,
            "reason": f"Atleta '{raw_ans}' não encontrado na base de {sector_name}.",
            "answer": raw_ans
        }

    # -------------------------------------------------------------
    # VALIDAÇÃO DE JOGADOR POR POSIÇÃO (Goleiro, Atacante)
    # -------------------------------------------------------------
    def _validate_player_by_position(self, norm_ans: str, raw_ans: str, target_pos: str, letter: str) -> dict:
        target_pos_norm = normalize_text(target_pos)
        mapped_ans = PLAYER_ALIASES.get(norm_ans, norm_ans)

        # Nível 1: Consulta direta no DynamoDB (nome original e apelido mapeado)
        try:
            items = []
            for query_name in {norm_ans, mapped_ans}:
                res = self.client.query(
                    TableName=TABLE_NAME,
                    KeyConditionExpression="pk = :pk",
                    ExpressionAttributeValues={":pk": {"S": f"PLAYER#{query_name}"}}
                )
                items.extend(res.get("Items", []))

            # Nível 2: Busca fuzzy se não achou direto
            if not items:
                scan_res = self.client.scan(
                    TableName=TABLE_NAME,
                    FilterExpression="#tp = :t and letra_inicial = :l",
                    ExpressionAttributeNames={"#tp": "type"},
                    ExpressionAttributeValues={":t": {"S": "PLAYER"}, ":l": {"S": letter}},
                    Limit=150
                )
                for it in scan_res.get("Items", []):
                    db_name = it.get("apelido_normalizado", {}).get("S", "")
                    if difflib.SequenceMatcher(None, norm_ans, db_name).ratio() >= 0.82 or difflib.SequenceMatcher(None, mapped_ans, db_name).ratio() >= 0.82:
                        items.append(it)

            if items:
                for it in items:
                    pos_gen = normalize_text(it.get("posicao", {}).get("S", ""))
                    pos_det = normalize_text(it.get("posicao_detalhada", {}).get("S", ""))
                    nome = it.get("nome", {}).get("S", it.get("apelido", {}).get("S", raw_ans))
                    clube = it.get("clube", {}).get("S", "")
                    passagem = f" (passagens por {clube})" if clube else ""

                    if target_pos_norm in pos_gen or target_pos_norm in pos_det or pos_gen in target_pos_norm or pos_det in target_pos_norm:
                        return {
                            "valid": True,
                            "points": 10,
                            "reason": f"Golaço! {nome} ({pos_det.title()}{passagem}) é um {target_pos.title()} válido.",
                            "answer": raw_ans
                        }

                # Se o atleta existe mas jogava em outra posição
                pos_real = items[0].get("posicao_detalhada", {}).get("S", items[0].get("posicao", {}).get("S", "outra posição"))
                nome = items[0].get("nome", {}).get("S", raw_ans)
                return {
                    "valid": False,
                    "points": 0,
                    "reason": f"Falta técnica! {nome} jogava como {pos_real}, e não como {target_pos.title()}.",
                    "answer": raw_ans
                }

        except Exception as e:
            print("Erro DynamoDB jogador por posição:", e)

        # Nível 3: VAR Online
        ext = None
        for search_cand in [raw_ans, mapped_ans, f"{mapped_ans} futebol"]:
            ext = self._search_external_soccer(search_cand)
            if ext and (ext["is_player"] or "futebolista" in ext["description"].lower() or "futebol" in ext["extract"].lower()):
                break

        if ext and (ext["is_player"] or "futebolista" in ext["description"].lower() or "futebol" in ext["extract"].lower()):
            full = f"{ext['description']} {ext['extract']}".lower()
            is_pos = False
            if target_pos_norm == "goleiro" and any(k in full for k in ["goleiro", "guarda-redes", "goalkeeper"]):
                is_pos = True
            elif target_pos_norm == "atacante" and any(k in full for k in ["atacante", "centroavante", "ponta", "striker", "forward"]):
                is_pos = True
            elif target_pos_norm in full:
                is_pos = True

            if is_pos:
                save_payload = {
                    "nome": ext["title"],
                    "apelido": ext["title"],
                    "apelido_normalizado": norm_ans,
                    "posicao": target_pos.title(),
                    "posicao_detalhada": ext.get("position", target_pos.title()),
                    "letra_inicial": letter,
                    "clube": "Futebol Internacional"
                }
                self._save_to_dynamo(
                    pk=f"PLAYER#{norm_ans}",
                    sk="INFO#GLOBAL",
                    item_type="PLAYER",
                    extra=save_payload
                )
                if mapped_ans != norm_ans:
                    self._save_to_dynamo(
                        pk=f"PLAYER#{mapped_ans}",
                        sk="INFO#GLOBAL",
                        item_type="PLAYER",
                        extra=save_payload
                    )
                return {
                    "valid": True,
                    "points": 10,
                    "reason": f"Golaço confirmado pelo VAR! {ext['title']} é um {target_pos.title()} ({ext['description']}).",
                    "answer": raw_ans
                }
            else:
                return {
                    "valid": False,
                    "points": 0,
                    "reason": f"Posição incorreta! {ext['title']} atuava como {ext.get('position', 'outra posição')}, não {target_pos.title()}.",
                    "answer": raw_ans
                }

        return {
            "valid": False,
            "points": 0,
            "reason": f"Atleta '{raw_ans}' não encontrado como {target_pos.title()}.",
            "answer": raw_ans
        }

    # -------------------------------------------------------------
    # VALIDAÇÃO DE CLUBE
    # -------------------------------------------------------------
    def _validate_club(self, norm_ans: str, raw_ans: str, letter: str) -> dict:
        # Nível 1: Alias direto (ex: america mineiro -> america-mg)
        target = CLUB_ALIASES.get(norm_ans, norm_ans)

        try:
            # 1. Busca direta no DynamoDB
            res = self.client.get_item(
                TableName=TABLE_NAME,
                Key={"pk": {"S": f"CLUB#{target}"}, "sk": {"S": "INFO"}}
            )
            if "Item" in res:
                nome = res["Item"].get("nome", {}).get("S", raw_ans)
                return {
                    "valid": True,
                    "points": 10,
                    "reason": f"Golaço! {nome} é um clube válido cadastrado.",
                    "answer": raw_ans
                }

            # 2. Busca aproximada / parcial no DynamoDB
            scan_res = self.client.scan(
                TableName=TABLE_NAME,
                FilterExpression="begins_with(pk, :prefix)",
                ExpressionAttributeValues={":prefix": {"S": "CLUB#"}},
                Limit=100
            )
            items = scan_res.get("Items", [])
            for it in items:
                db_name = normalize_text(it.get("nome_normalizado", {}).get("S", ""))
                # Correspondência por palavra inteira ou início do nome com tamanho mínimo
                if len(target) >= 4 and (target in db_name.split() or db_name.startswith(target) or target.startswith(db_name)):
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Golaço! {it.get('nome', {}).get('S', raw_ans)} é um clube válido.",
                        "answer": raw_ans
                    }
                ratio = difflib.SequenceMatcher(None, target, db_name).ratio()
                if ratio >= 0.82:
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Válido! {it.get('nome', {}).get('S', raw_ans)} (reconhecido por aproximação).",
                        "answer": raw_ans
                    }

        except Exception as e:
            print("Erro DynamoDB clube:", e)

        # Nível 3: Consulta ao VAR Online (Wikipedia Esportes)
        ext = self._search_external_soccer(raw_ans)
        if ext and (ext["is_club"] or "futebol" in ext["description"].lower()):
            # Auto-aprendizado: salva no DynamoDB
            self._save_to_dynamo(
                pk=f"CLUB#{target}",
                sk="INFO",
                item_type="CLUB",
                extra={"nome": ext["title"], "nome_normalizado": target, "letra_inicial": letter}
            )
            return {
                "valid": True,
                "points": 10,
                "reason": f"Golaço confirmado pelo VAR! {ext['title']} ({ext['description']}) adicionado à base.",
                "answer": raw_ans
            }

        return {
            "valid": False,
            "points": 0,
            "reason": f"Clube '{raw_ans}' não reconhecido na base de futebol.",
            "answer": raw_ans
        }

    # -------------------------------------------------------------
    # VALIDAÇÃO DE JOGADOR GENÉRICO (COM BUSCA MUNDIAL E AUTO-APRENDIZADO)
    # -------------------------------------------------------------
    def _validate_generic_player(self, norm_ans: str, raw_ans: str, letter: str) -> dict:
        mapped_ans = PLAYER_ALIASES.get(norm_ans, norm_ans)

        # Nível 1: Busca exata no DynamoDB (nome original e apelido mapeado)
        try:
            for q_name in {norm_ans, mapped_ans}:
                res = self.client.query(
                    TableName=TABLE_NAME,
                    KeyConditionExpression="pk = :pk",
                    ExpressionAttributeValues={":pk": {"S": f"PLAYER#{q_name}"}},
                    Limit=1
                )
                if res.get("Items"):
                    it = res["Items"][0]
                    nome = it.get("nome", {}).get("S", raw_ans)
                    cl = it.get("clube", {}).get("S", "")
                    pos = it.get("posicao_detalhada", {}).get("S", "Jogador")
                    cl_str = f", passagem por {cl}" if cl else ""
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Golaço! {nome} ({pos}{cl_str}) é um jogador válido.",
                        "answer": raw_ans
                    }

            # Nível 2: Busca fuzzy/aproximada por nome no DynamoDB (para atletas com mesma letra)
            scan_res = self.client.scan(
                TableName=TABLE_NAME,
                FilterExpression="#tp = :t and letra_inicial = :l",
                ExpressionAttributeNames={"#tp": "type"},
                ExpressionAttributeValues={":t": {"S": "PLAYER"}, ":l": {"S": letter}},
                Limit=120
            )
            for it in scan_res.get("Items", []):
                db_name = it.get("apelido_normalizado", {}).get("S", "")
                ratio = difflib.SequenceMatcher(None, norm_ans, db_name).ratio()
                if ratio >= 0.82:
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Válido! {it.get('apelido', {}).get('S', raw_ans)} (reconhecido na base).",
                        "answer": raw_ans
                    }

        except Exception as e:
            print("Erro DynamoDB jogador:", e)

        # Nível 3: Consulta ao VAR Online (Wikipedia / Craques Mundiais como Van Nistelrooy)
        ext = self._search_external_soccer(raw_ans)
        if ext and (ext["is_player"] or "futebolista" in ext["description"].lower() or "futebol" in ext["extract"].lower()):
            # Valida se o nome oficial ou apelido coincide com a letra
            norm_title = normalize_text(ext["title"])
            # Título pode ser "Ruud van Nistelrooy" ou "Van Nistelrooy"
            words = norm_title.split()
            matches_letter = any(w.startswith(letter.lower()) for w in words) or norm_ans.startswith(letter.lower())

            if matches_letter:
                # Auto-aprendizado: salva no DynamoDB para futuras consultas instantâneas!
                self._save_to_dynamo(
                    pk=f"PLAYER#{norm_ans}",
                    sk="INFO#GLOBAL",
                    item_type="PLAYER",
                    extra={
                        "nome": ext["title"],
                        "apelido": ext["title"],
                        "apelido_normalizado": norm_ans,
                        "posicao": "Jogador",
                        "posicao_detalhada": ext.get("position", "Atleta"),
                        "letra_inicial": letter,
                        "clube": "Futebol Internacional",
                        "clube_normalizado": "futebol internacional"
                    }
                )
                return {
                    "valid": True,
                    "points": 10,
                    "reason": f"Golaço confirmado pelo VAR! {ext['title']} ({ext['description']}) adicionado à base.",
                    "answer": raw_ans
                }

        return {
            "valid": False,
            "points": 0,
            "reason": f"Jogador '{raw_ans}' não encontrado nos registros do futebol.",
            "answer": raw_ans
        }

    # -------------------------------------------------------------
    # VALIDAÇÃO DE POSIÇÃO EM CLUBE ESPECÍFICO (Ex: Lateral Esquerdo do Flamengo)
    # -------------------------------------------------------------
    def _validate_player_club_position(self, norm_ans: str, raw_ans: str, target_club: str, target_pos: str, letter: str) -> dict:
        try:
            # 1. Consulta o jogador no DynamoDB
            res = self.client.query(
                TableName=TABLE_NAME,
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": {"S": f"PLAYER#{norm_ans}"}}
            )
            items = res.get("Items", [])
            
            # Busca fuzzy se não encontrou direto
            if not items:
                scan_res = self.client.scan(
                    TableName=TABLE_NAME,
                    FilterExpression="#tp = :t and letra_inicial = :l",
                    ExpressionAttributeNames={"#tp": "type"},
                    ExpressionAttributeValues={":t": {"S": "PLAYER"}, ":l": {"S": letter}},
                    Limit=150
                )
                for it in scan_res.get("Items", []):
                    db_name = it.get("apelido_normalizado", {}).get("S", "")
                    if difflib.SequenceMatcher(None, norm_ans, db_name).ratio() >= 0.82:
                        items.append(it)

            # Se encontrou no DynamoDB, avalia passagem e posição
            if items:
                club_records = []
                for it in items:
                    cl_norm = normalize_text(it.get("clube_normalizado", {}).get("S", ""))
                    cl_alias = CLUB_ALIASES.get(cl_norm, cl_norm)
                    if target_club in cl_norm or cl_norm in target_club or cl_alias == target_club:
                        club_records.append(it)

                if not club_records:
                    clubes_jogou = list({it.get("clube", {}).get("S", "") for it in items if it.get("clube", {}).get("S")})
                    cl_txt = ", ".join(clubes_jogou[:3]) if clubes_jogou else "outros clubes"
                    return {
                        "valid": False,
                        "points": 0,
                        "reason": f"Impedimento! {raw_ans} jogou em {cl_txt}, mas não no {target_club.title()}.",
                        "answer": raw_ans
                    }

                # Avalia a posição
                for rec in club_records:
                    pos_gen = normalize_text(rec.get("posicao", {}).get("S", ""))
                    pos_det = normalize_text(rec.get("posicao_detalhada", {}).get("S", ""))
                    anos = rec.get("anos", {}).get("S", "")
                    ano_str = f" ({anos})" if anos else ""

                    if "esquerdo" in target_pos:
                        if "esquerdo" in pos_det or pos_det == "lateral esquerdo":
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço confirmado pelo VAR! {raw_ans} atuou como Lateral-Esquerdo do {target_club.title()}{ano_str}.",
                                "answer": raw_ans
                            }
                        elif "direito" in pos_det:
                            return {
                                "valid": False,
                                "points": 0,
                                "reason": f"Falta técnica! {raw_ans} jogou no {target_club.title()}, mas atuava como Lateral-Direito e não Lateral-Esquerdo.",
                                "answer": raw_ans
                            }
                    elif "direito" in target_pos:
                        if "direito" in pos_det or pos_det == "lateral direito":
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço confirmado pelo VAR! {raw_ans} atuou como Lateral-Direito do {target_club.title()}{ano_str}.",
                                "answer": raw_ans
                            }
                        elif "esquerdo" in pos_det:
                            return {
                                "valid": False,
                                "points": 0,
                                "reason": f"Falta técnica! {raw_ans} jogou no {target_club.title()}, mas atuava como Lateral-Esquerdo e não Lateral-Direito.",
                                "answer": raw_ans
                            }
                    elif target_pos == "volante":
                        if any(k in pos_det or k in pos_gen for k in ["volante", "meio-campo", "meia", "defensive"]):
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço! {raw_ans} defendeu o {target_club.title()} como Volante / Meio-campo{ano_str}.",
                                "answer": raw_ans
                            }
                    elif target_pos in ["meia", "meio-campo"]:
                        if any(k in pos_det or k in pos_gen for k in ["meia", "meio-campo", "volante", "midfield"]):
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço! {raw_ans} defendeu o {target_club.title()} na meiuca como {pos_det.title()}{ano_str}.",
                                "answer": raw_ans
                            }
                    elif target_pos == "atacante":
                        if any(k in pos_det or k in pos_gen for k in ["atacante", "centroavante", "ponta", "forward", "striker", "winger"]):
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço! {raw_ans} foi Atacante do {target_club.title()}{ano_str}.",
                                "answer": raw_ans
                            }
                    elif target_pos == "zagueiro":
                        if "zagueiro" in pos_det or "centre-back" in pos_det or "zagueiro" in pos_gen:
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço! {raw_ans} foi Zagueiro do {target_club.title()}{ano_str}.",
                                "answer": raw_ans
                            }
                    elif target_pos == "goleiro":
                        if "goleiro" in pos_det or "guarda-redes" in pos_det or "goalkeeper" in pos_det or "goleiro" in pos_gen:
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço! {raw_ans} foi Goleiro do {target_club.title()}{ano_str}.",
                                "answer": raw_ans
                            }
                    elif target_pos == "lateral":
                        if "lateral" in pos_det or "back" in pos_det:
                            return {
                                "valid": True,
                                "points": 10,
                                "reason": f"Golaço! {raw_ans} defendeu o {target_club.title()} como Lateral{ano_str}.",
                                "answer": raw_ans
                            }
                    elif target_pos in pos_gen or target_pos in pos_det or pos_gen in target_pos:
                        return {
                            "valid": True,
                            "points": 10,
                            "reason": f"Válido! {raw_ans} defendeu o {target_club.title()} como {pos_det.title()}{ano_str}.",
                            "answer": raw_ans
                        }

                pos_jogadas = list({rec.get("posicao_detalhada", {}).get("S", rec.get("posicao", {}).get("S", "")) for rec in club_records})
                return {
                    "valid": False,
                    "points": 0,
                    "reason": f"Posição incorreta! No {target_club.title()}, {raw_ans} jogava como {', '.join(pos_jogadas)}.",
                    "answer": raw_ans
                }

            # Nível 3: Se não encontrou no banco, checa no VAR Online
            ext = self._search_external_soccer(f"{raw_ans} {target_club}")
            if ext and ext["is_player"]:
                ext_full = f"{ext['description']} {ext['extract']}".lower()
                club_mentioned = target_club in ext_full or any(a in ext_full for a in CLUB_ALIASES if CLUB_ALIASES[a] == target_club)
                pos_mentioned = any(p in ext_full for p in [target_pos, "lateral", "zagueiro", "atacante", "meia", "goleiro"])

                if club_mentioned and pos_mentioned:
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Golaço confirmado pelo VAR! {ext['title']} jogou no {target_club.title()} ({ext['description']}).",
                        "answer": raw_ans
                    }

        except Exception as e:
            print("Erro DynamoDB jogador x posição:", e)

        return {
            "valid": False,
            "points": 0,
            "reason": f"Atleta '{raw_ans}' não encontrado no histórico do {target_club.title()} para essa posição.",
            "answer": raw_ans
        }

    # -------------------------------------------------------------
    # VALIDAÇÃO DE ESTÁDIO E TÉCNICO
    # -------------------------------------------------------------
    def _validate_stadium(self, norm_ans: str, raw_ans: str, letter: str) -> dict:
        try:
            res = self.client.get_item(
                TableName=TABLE_NAME,
                Key={"pk": {"S": f"STADIUM#{norm_ans}"}, "sk": {"S": "INFO"}}
            )
            if "Item" in res:
                return {
                    "valid": True,
                    "points": 10,
                    "reason": f"Válido! {res['Item'].get('nome', {}).get('S', raw_ans)} é uma arena/estádio cadastrado.",
                    "answer": raw_ans
                }

            # Busca parcial
            scan_res = self.client.scan(
                TableName=TABLE_NAME,
                FilterExpression="begins_with(pk, :prefix)",
                ExpressionAttributeValues={":prefix": {"S": "STADIUM#"}},
                Limit=50
            )
            for it in scan_res.get("Items", []):
                db_name = it.get("nome_normalizado", {}).get("S", "")
                if len(norm_ans) >= 4 and (norm_ans in db_name.split() or db_name.startswith(norm_ans) or norm_ans.startswith(db_name)):
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Válido! {it.get('nome', {}).get('S', raw_ans)} é um estádio de futebol.",
                        "answer": raw_ans
                    }
                ratio = difflib.SequenceMatcher(None, norm_ans, db_name).ratio()
                if ratio >= 0.82:
                    return {
                        "valid": True,
                        "points": 10,
                        "reason": f"Válido! {it.get('nome', {}).get('S', raw_ans)} (reconhecido por aproximação).",
                        "answer": raw_ans
                    }
        except Exception as e:
            print("Erro estádio:", e)

        # VAR Online
        ext = self._search_external_soccer(raw_ans)
        if ext and (ext["is_stadium"] or "estadio" in ext["description"].lower() or "arena" in ext["title"].lower()):
            self._save_to_dynamo(f"STADIUM#{norm_ans}", "INFO", "STADIUM", {"nome": ext["title"], "nome_normalizado": norm_ans, "letra_inicial": letter})
            return {
                "valid": True,
                "points": 10,
                "reason": f"Válido! {ext['title']} ({ext['description']}) adicionado à base.",
                "answer": raw_ans
            }

        return {"valid": False, "points": 0, "reason": f"Estádio '{raw_ans}' não reconhecido.", "answer": raw_ans}

    def _validate_coach(self, norm_ans: str, raw_ans: str, letter: str) -> dict:
        try:
            res = self.client.query(
                TableName=TABLE_NAME,
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": {"S": f"COACH#{norm_ans}"}},
                Limit=1
            )
            if res.get("Items"):
                it = res["Items"][0]
                tc = it.get("nome", {}).get("S", raw_ans)
                cl = it.get("clube", {}).get("S", "")
                detail = f" (com passagem por {cl})" if cl else ""
                return {
                    "valid": True,
                    "points": 10,
                    "reason": f"Excelente! {tc} é um técnico de futebol registrado{detail}.",
                    "answer": raw_ans
                }
        except Exception as e:
            print("Erro técnico:", e)

        # VAR Online
        ext = self._search_external_soccer(raw_ans)
        if ext and (ext["is_coach"] or "treinador" in ext["description"].lower() or "tecnico" in ext["extract"].lower()):
            self._save_to_dynamo(f"COACH#{norm_ans}", "INFO", "COACH", {"nome": ext["title"], "nome_normalizado": norm_ans, "letra_inicial": letter})
            return {
                "valid": True,
                "points": 10,
                "reason": f"Excelente! {ext['title']} ({ext['description']}) adicionado à base.",
                "answer": raw_ans
            }

        return {"valid": False, "points": 0, "reason": f"Técnico '{raw_ans}' não encontrado.", "answer": raw_ans}

    # -------------------------------------------------------------
    # HELPER: CONSULTA DE FUTEBOL EM TEMPO REAL (WIKIPEDIA REST API)
    # -------------------------------------------------------------
    def _search_external_soccer(self, term: str) -> dict:
        """
        Pesquisa na API pública de conhecimento em português.
        Retorna informações estruturadas sobre o clube ou atleta.
        """
        def _query_wiki(search_text):
            try:
                encoded = urllib.parse.quote(search_text.strip())
                url = f"https://pt.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit=5&namespace=0&format=json"
                req = urllib.request.Request(url, headers={"User-Agent": "StopFutBot/2.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    if not data[1]:
                        return None

                    for title in data[1]:
                        try:
                            summary_url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
                            req2 = urllib.request.Request(summary_url, headers={"User-Agent": "StopFutBot/2.0"})
                            with urllib.request.urlopen(req2, timeout=3) as resp2:
                                sdata = json.loads(resp2.read().decode())
                                desc = sdata.get("description", "").lower()
                                extract = sdata.get("extract", "").lower()
                                full = f"{desc} {extract}"

                                if "desambigua" in desc or "desambigua" in extract:
                                    continue

                                is_football = any(k in full for k in ["futebol", "futebolista", "jogador", "treinador", "clube", "estadio", "soccer"])
                                if not is_football:
                                    continue

                                is_player = any(k in full for k in ["futebolista", "jogador de futebol", "atuava como", "atua como", "lateral", "zagueiro", "goleiro", "meio-campista", "atacante", "centroavante", "ponta"])
                                is_club = any(k in full for k in ["clube de futebol", "associacao desportiva", "time de futebol", "futebol clube", "clube desportivo"])
                                is_stadium = any(k in full for k in ["estadio", "arena", "complexo esportivo"])
                                is_coach = any(k in full for k in ["treinador de futebol", "tecnico de futebol", "treinador"])

                                pos_desc = "Atleta de Futebol"
                                if "centroavante" in full or "atacante" in full:
                                    pos_desc = "Atacante"
                                elif "lateral" in full:
                                    pos_desc = "Lateral"
                                elif "goleiro" in full:
                                    pos_desc = "Goleiro"
                                elif "zagueiro" in full:
                                    pos_desc = "Zagueiro"
                                elif "meio-campista" in full or "volante" in full or "meia" in full:
                                    pos_desc = "Meio-campo"

                                return {
                                    "title": sdata.get("title"),
                                    "description": sdata.get("description", ""),
                                    "extract": sdata.get("extract", ""),
                                    "position": pos_desc,
                                    "is_player": is_player,
                                    "is_club": is_club,
                                    "is_stadium": is_stadium,
                                    "is_coach": is_coach
                                }
                        except Exception:
                            continue
            except Exception:
                pass
            return None

        try:
            # Tenta busca direta e, se não encontrar, tenta com sufixo "futebol"
            res = _query_wiki(term)
            if not res and not term.lower().endswith("futebol"):
                res = _query_wiki(f"{term} futebol")
            return res
        except Exception:
            return None
        except Exception:
            return None

    def _save_to_dynamo(self, pk: str, sk: str, item_type: str, extra: dict):
        """Auto-aprendizado: persiste item verificado no DynamoDB local."""
        try:
            item = {
                "pk": {"S": pk},
                "sk": {"S": sk},
                "type": {"S": item_type}
            }
            for k, v in extra.items():
                if v:
                    item[k] = {"S": str(v)}
            self.client.put_item(TableName=TABLE_NAME, Item=item)
            print(f"[AUTO-APRENDIZADO DYNAMODB] Salvo: {pk} ({item_type})")
        except Exception as e:
            print("Aviso ao salvar auto-aprendizado no DynamoDB:", e)

if __name__ == "__main__":
    validator = FootballAgentValidator()
    print("--- Testando os Casos Solicitados ---")

    # 1. Clube com A: América Mineiro
    print("\n1. Clube: 'america mineiro'")
    res1 = validator.validate_answer("A", "clube", "Clube de Futebol", "america mineiro")
    print("Resultado:", res1)

    # 2. Jogador com V: van nisterooy (com erro de digitação proposital)
    print("\n2. Jogador: 'van nisterooy'")
    res2 = validator.validate_answer("V", "jogador", "Jogador / Craque", "van nisterooy")
    print("Resultado:", res2)

    # 3. Jogador com V: van nistelrooy (correto)
    print("\n3. Jogador: 'van nistelrooy'")
    res3 = validator.validate_answer("V", "jogador", "Jogador / Craque", "van nistelrooy")
    print("Resultado:", res3)

"""
Servidor API, Multiplayer e Backend do StopFut (compatível com Local e AWS Lambda Function URL).
Disponibiliza endpoints REST para:
- Salas Multiplayer estilo StopotS (Lobby, Públicas, Privadas com senha)
- Partida Rápida (Quick Match)

- Sincronização de rodada, letra, categorias, contagem regressiva e STOP
- Validação pelo Árbitro VAR com DynamoDB
- Ranking da Sala e Ranking Global
- Google Sign-In (Opcional)
"""

import http.server
import socketserver
import json
import os
import random
import base64
from urllib.parse import urlparse, parse_qs
from agent_validator import FootballAgentValidator, EMULATOR_URL
from rooms_manager import RoomsManager

PORT = 8080
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

validator = FootballAgentValidator()
rooms_mgr = RoomsManager(dynamo_client=validator.client)

# Categorias Setoriais Gerais (Dinâmicas e Criativas)
BASE_SECTORS = [
    {"id": "clube", "name": "Clube / Time de Futebol", "icon": "⚽"},
    {"id": "defesa", "name": "Linha Defensiva (Zagueiro ou Lateral)", "icon": "🛡️"},
    {"id": "meiuca", "name": "Meiuca (Volante ou Meio-Campo)", "icon": "🧠"},
    {"id": "ataque", "name": "Ataque (Centroavante ou Ponta)", "icon": "🎯"},
    {"id": "goleiro", "name": "Goleiro / Guarda-Redes", "icon": "🧤"},
    {"id": "volante", "name": "Volante / Cão de Guarda", "icon": "🔒"},
    {"id": "jogador", "name": "Craque / Jogador Livre", "icon": "⭐"},
    {"id": "estadio", "name": "Estádio / Arena", "icon": "🏟️"},
    {"id": "tecnico", "name": "Técnico / Treinador", "icon": "👔"},
]

# Perguntas Desafio (Dificuldade Máxima: Posição x Clube Específico)
CHALLENGE_CATEGORIES = [
    # Laterais
    {"id": "lat_esq_fla", "name": "Lateral Esquerdo do Flamengo", "icon": "🔴⚫"},
    {"id": "lat_dir_fla", "name": "Lateral Direito do Flamengo", "icon": "🔴⚫"},
    {"id": "lat_esq_pal", "name": "Lateral Esquerdo do Palmeiras", "icon": "🟢⚪"},
    {"id": "lat_dir_pal", "name": "Lateral Direito do Palmeiras", "icon": "🟢⚪"},
    {"id": "lat_esq_sp", "name": "Lateral Esquerdo do São Paulo", "icon": "🔴⚪⚫"},
    {"id": "lat_dir_cor", "name": "Lateral Direito do Corinthians", "icon": "⚪⚫"},
    {"id": "lat_esq_vas", "name": "Lateral Esquerdo do Vasco", "icon": "⚪⚫"},
    {"id": "lat_esq_gre", "name": "Lateral Esquerdo do Grêmio", "icon": "🔵⚪⚫"},
    {"id": "lat_esq_flu", "name": "Lateral Esquerdo do Fluminense", "icon": "🟢⚪🔴"},
    {"id": "lat_esq_int", "name": "Lateral Esquerdo do Internacional", "icon": "🔴⚪"},
    {"id": "lat_rm", "name": "Lateral do Real Madrid", "icon": "👑"},
    {"id": "lat_barca", "name": "Lateral do Barcelona", "icon": "🔵🔴"},

    # Atacantes
    {"id": "ata_fla", "name": "Atacante do Flamengo", "icon": "🔴⚫"},
    {"id": "ata_pal", "name": "Atacante do Palmeiras", "icon": "🟢⚪"},
    {"id": "ata_sp", "name": "Atacante do São Paulo", "icon": "🔴⚪⚫"},
    {"id": "ata_cor", "name": "Atacante do Corinthians", "icon": "⚪⚫"},
    {"id": "ata_san", "name": "Atacante do Santos", "icon": "⚪⚫"},
    {"id": "ata_vas", "name": "Atacante do Vasco", "icon": "⚪⚫"},
    {"id": "ata_rm", "name": "Atacante do Real Madrid", "icon": "👑"},
    {"id": "ata_barca", "name": "Atacante do Barcelona", "icon": "🔵🔴"},
    {"id": "ata_city", "name": "Atacante do Manchester City", "icon": "🩵"},

    # Volantes e Meias
    {"id": "vol_cor", "name": "Volante do Corinthians", "icon": "⚪⚫"},
    {"id": "vol_fla", "name": "Volante do Flamengo", "icon": "🔴⚫"},
    {"id": "vol_sp", "name": "Volante do São Paulo", "icon": "🔴⚪⚫"},
    {"id": "vol_pal", "name": "Volante do Palmeiras", "icon": "🟢⚪"},
    {"id": "meia_fla", "name": "Meia do Flamengo", "icon": "🔴⚫"},
    {"id": "meia_sp", "name": "Meia do São Paulo", "icon": "🔴⚪⚫"},
    {"id": "meia_pal", "name": "Meia do Palmeiras", "icon": "🟢⚪"},
    {"id": "meia_san", "name": "Meia do Santos", "icon": "⚪⚫"},

    # Zagueiros e Goleiros
    {"id": "zag_pal", "name": "Zagueiro do Palmeiras", "icon": "🟢⚪"},
    {"id": "zag_fla", "name": "Zagueiro do Flamengo", "icon": "🔴⚫"},
    {"id": "zag_sp", "name": "Zagueiro do São Paulo", "icon": "🔴⚪⚫"},
    {"id": "zag_cor", "name": "Zagueiro do Corinthians", "icon": "⚪⚫"},
    {"id": "gol_gre", "name": "Goleiro do Grêmio", "icon": "🔵⚪⚫"},
    {"id": "gol_pal", "name": "Goleiro do Palmeiras", "icon": "🟢⚪"},
    {"id": "gol_cor", "name": "Goleiro do Corinthians", "icon": "⚪⚫"},
    {"id": "gol_fla", "name": "Goleiro do Flamengo", "icon": "🔴⚫"},
    {"id": "gol_sp", "name": "Goleiro do São Paulo", "icon": "🔴⚪⚫"},
]

CATEGORIES_POOL = BASE_SECTORS + CHALLENGE_CATEGORIES

LETTERS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "L", "M", "N", "O", "P", "R", "S", "T", "U", "V", "Z"
]

def generate_round():
    letter = random.choice(LETTERS)
    clube_cat = BASE_SECTORS[0]
    other_sectors = random.sample(BASE_SECTORS[1:], 3)
    challenge_cat = random.choice(CHALLENGE_CATEGORIES)
    selected = [clube_cat] + other_sectors + [challenge_cat]
    random.shuffle(selected)
    return {
        "letter": letter,
        "categories": selected,
        "round_time": 60
    }

def handle_api_request(method: str, path: str, query_params: dict, body_data: dict) -> tuple:
    """Roteador unificado para Local e AWS Lambda."""
    method = method.upper()

    # --- ROTAS GET ---
    if method == "GET":
        if path == "/api/round":
            return 200, generate_round()

        if path == "/api/categories":
            return 200, {"categories": CATEGORIES_POOL, "letters": LETTERS}

        if path == "/api/status":
            try:
                tables = validator.client.list_tables().get("TableNames", [])
                return 200, {
                    "status": "online",
                    "tables": tables,
                    "database_ready": "stopfut_database" in tables
                }
            except Exception as e:
                return 500, {"status": "error", "error": str(e)}

        if path == "/api/rooms":
            return 200, {"rooms": rooms_mgr.list_rooms()}

        if path == "/api/rooms/state":
            room_id = query_params.get("room_id", [""])[0] if isinstance(query_params.get("room_id"), list) else query_params.get("room_id", "")
            user_id = query_params.get("user_id", [""])[0] if isinstance(query_params.get("user_id"), list) else query_params.get("user_id", "")
            state = rooms_mgr.get_room_state(room_id, user_id)
            if "error" in state:
                return 404, state
            return 200, state

        if path == "/api/rooms/ranking":
            room_id = query_params.get("room_id", [""])[0] if isinstance(query_params.get("room_id"), list) else query_params.get("room_id", "")
            return 200, {"room_id": room_id, "ranking": rooms_mgr.get_room_ranking(room_id)}

        if path == "/api/rooms/audit":
            room_id = query_params.get("room_id", [""])[0] if isinstance(query_params.get("room_id"), list) else query_params.get("room_id", "")
            res = rooms_mgr.get_room_audit(room_id)
            if "error" in res:
                return 404, res
            return 200, res

        if path == "/api/ranking":
            return 200, {"ranking": rooms_mgr.get_global_ranking()}

    # --- ROTAS POST ---
    elif method == "POST":
        if path == "/api/validate":
            letter = body_data.get("letter", "").strip().upper()
            answers = body_data.get("answers", [])
            total_points = 0
            results = []
            for item in answers:
                cat_id = item.get("id", "")
                cat_name = item.get("name", "")
                ans = item.get("answer", "")
                val = validator.validate_answer(letter, cat_id, cat_name, ans)
                total_points += val["points"]
                results.append({
                    "id": cat_id,
                    "name": cat_name,
                    "answer": ans,
                    "valid": val["valid"],
                    "points": val["points"],
                    "reason": val["reason"]
                })
            return 200, {"letter": letter, "total_points": total_points, "results": results}

        if path == "/api/rooms/create":
            room = rooms_mgr.create_room(
                name=body_data.get("name", ""),
                is_private=body_data.get("is_private", False),
                password=body_data.get("password", ""),
                rounds_total=body_data.get("rounds_total", 5),
                round_time=body_data.get("round_time", 60),
                host_id=body_data.get("user_id", ""),
                host_name=body_data.get("nickname", "Craque"),
                host_avatar=body_data.get("avatar", "⚽")
            )
            return 200, room

        if path == "/api/rooms/join":
            res = rooms_mgr.join_room(
                room_id=body_data.get("room_id", ""),
                user_id=body_data.get("user_id", ""),
                nickname=body_data.get("nickname", "Craque"),
                avatar=body_data.get("avatar", "⚽"),
                password=body_data.get("password", "")
            )
            if "error" in res:
                return 400, res
            return 200, res

        if path == "/api/rooms/quick_match":
            res = rooms_mgr.quick_match(
                user_id=body_data.get("user_id", ""),
                nickname=body_data.get("nickname", "Craque"),
                avatar=body_data.get("avatar", "⚽")
            )
            return 200, res

        if path == "/api/rooms/start":
            res = rooms_mgr.start_game(
                room_id=body_data.get("room_id", ""),
                user_id=body_data.get("user_id", ""),
                get_round_func=generate_round
            )
            if "error" in res:
                return 400, res
            return 200, res

        if path == "/api/rooms/stop":
            res = rooms_mgr.stop_round(
                room_id=body_data.get("room_id", ""),
                user_id=body_data.get("user_id", "")
            )
            if "error" in res:
                return 400, res
            return 200, res

        if path == "/api/rooms/submit":
            res = rooms_mgr.submit_answers(
                room_id=body_data.get("room_id", ""),
                user_id=body_data.get("user_id", ""),
                answers=body_data.get("answers", []),
                validator=validator
            )
            if "error" in res:
                return 400, res
            return 200, res

        if path == "/api/rooms/next_round":
            res = rooms_mgr.next_round(
                room_id=body_data.get("room_id", ""),
                user_id=body_data.get("user_id", ""),
                get_round_func=generate_round
            )
            if "error" in res:
                return 400, res
            return 200, res

        if path == "/api/rooms/leave":
            res = rooms_mgr.leave_room(
                room_id=body_data.get("room_id", ""),
                user_id=body_data.get("user_id", "")
            )
            return 200, res

        # Autenticação Google (Opcional - decodifica perfil sem dependências externas)
        if path == "/api/auth/google":
            credential = body_data.get("credential", "")
            if credential:
                try:
                    # JWT: payload é a segunda parte codificada em base64
                    payload_b64 = credential.split(".")[1]
                    # Adiciona padding para decodificar
                    payload_b64 += "=" * (-len(payload_b64) % 4)
                    payload_json = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    user_profile = {
                        "id": f"g_{payload_json.get('sub', '')[:10]}",
                        "name": payload_json.get("name", "Craque Google"),
                        "email": payload_json.get("email", ""),
                        "picture": payload_json.get("picture", ""),
                        "avatar": "⚽"
                    }
                    return 200, {"success": True, "profile": user_profile}
                except Exception as e:
                    return 400, {"error": f"Token Google inválido: {e}"}
            return 400, {"error": "Credencial não informada."}

    return 404, {"error": "Endpoint não encontrado"}


# =========================================================================
# HANDLER SERVIDOR LOCAL (HTTP SERVER)
# =========================================================================
class StopFutRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            params = parse_qs(parsed.query)
            status, data = handle_api_request("GET", parsed.path, params, {})
            return self._send_json(data, status=status)
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            try:
                body_data = json.loads(raw_body)
            except Exception:
                body_data = {}
            params = parse_qs(parsed.query)
            status, data = handle_api_request("POST", parsed.path, params, body_data)
            return self._send_json(data, status=status)
        self.send_error(404, "Endpoint não encontrado")


# =========================================================================
# HANDLER AWS LAMBDA SERVERLESS (FUNCTION URL)
# =========================================================================
def lambda_handler(event, context):
    """
    Entrada oficial para execução Serverless no AWS Lambda Function URL.
    Compatível com Payload Format Version 2.0 e 1.0.
    Nota: O CORS é gerenciado na borda pela configuração da Function URL da AWS.
    Portanto, os headers de resposta não devem duplicar o Access-Control-Allow-Origin.
    """
    http_ctx = event.get("requestContext", {}).get("http", {})
    method = http_ctx.get("method", event.get("httpMethod", "GET")).upper()
    path = http_ctx.get("path", event.get("rawPath", event.get("path", "/")))

    res_headers = {
        "Content-Type": "application/json; charset=utf-8"
    }

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": res_headers, "body": "{}"}

    query_params = event.get("queryStringParameters") or {}
    raw_body = event.get("body", "{}")
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        body_data = json.loads(raw_body) if raw_body else {}
    except Exception:
        body_data = {}

    status, data = handle_api_request(method, path, query_params, body_data)
    return {
        "statusCode": status,
        "headers": res_headers,
        "body": json.dumps(data, ensure_ascii=False)
    }


def run_server():
    server_address = ("", PORT)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(server_address, StopFutRequestHandler) as httpd:
        print(f"--> Servidor StopFut rodando em http://localhost:{PORT}")
        print(f"--> Frontend servido de: {FRONTEND_DIR}")
        print("--> Conectado ao DynamoDB com suporte a Salas Multiplayer!")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()

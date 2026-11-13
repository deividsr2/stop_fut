"""
Servidor API e Backend do StopFut.
Disponibiliza endpoints REST para sorteio de letras, categorias e validação
com o Agente Validador conectado ao DynamoDB no AWS Emulator.
"""

import http.server
import socketserver
import json
import os
import random
from urllib.parse import urlparse, parse_qs
from agent_validator import FootballAgentValidator, EMULATOR_URL

PORT = 8080
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

validator = FootballAgentValidator()

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
        
        # 1. API: Obter Nova Rodada (Letra + Categorias Balanceadas)
        if parsed.path == "/api/round":
            letter = random.choice(LETTERS)
            # Regra de ouro da rodada:
            # - 1 Clube (sempre presente)
            # - 3 Setores dinâmicos (Defesa, Meiuca, Ataque, Goleiro, Volante, Estádio, Técnico, Craque)
            # - 1 Pergunta Desafio (Dificuldade máxima: Posição x Clube)
            clube_cat = BASE_SECTORS[0]
            other_sectors = random.sample(BASE_SECTORS[1:], 3)
            challenge_cat = random.choice(CHALLENGE_CATEGORIES)
            
            selected = [clube_cat] + other_sectors + [challenge_cat]
            random.shuffle(selected)
            
            return self._send_json({
                "letter": letter,
                "categories": selected,
                "round_time": 60
            })

        # 2. API: Categorias completas
        if parsed.path == "/api/categories":
            return self._send_json({"categories": CATEGORIES_POOL, "letters": LETTERS})

        # 3. API: Status do Banco de Dados
        if parsed.path == "/api/status":
            try:
                tables = validator.client.list_tables().get("TableNames", [])
                return self._send_json({
                    "status": "online",
                    "emulator_url": EMULATOR_URL,
                    "tables": tables,
                    "database_ready": "stopfut_database" in tables
                })
            except Exception as e:
                return self._send_json({"status": "error", "error": str(e)}, status=500)

        # Fallback: serve arquivos estáticos do frontend
        super().do_GET()

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            
            # API: Validação de Respostas pelo Agente
            if parsed.path == "/api/validate":
                content_len = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_len).decode("utf-8")
                try:
                    data = json.loads(raw_body)
                except Exception as je:
                    return self._send_json({"error": f"JSON inválido: {je}"}, status=400)

                letter = data.get("letter", "").strip().upper()
                answers = data.get("answers", []) # lista de { id, name, answer }

                results = []
                total_points = 0

                for item in answers:
                    cat_id = item.get("id", "")
                    cat_name = item.get("name", "")
                    user_answer = item.get("answer", "")

                    val = validator.validate_answer(
                        letter=letter,
                        category_id=cat_id,
                        category_name=cat_name,
                        answer=user_answer
                    )
                    total_points += val["points"]
                    results.append({
                        "id": cat_id,
                        "name": cat_name,
                        "answer": user_answer,
                        "valid": val["valid"],
                        "points": val["points"],
                        "reason": val["reason"]
                    })

                return self._send_json({
                    "letter": letter,
                    "total_points": total_points,
                    "results": results
                })

            self.send_error(404, "Endpoint não encontrado")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json({"error": f"Erro interno: {e}"}, status=500)

def run_server():
    server_address = ("", PORT)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(server_address, StopFutRequestHandler) as httpd:
        print(f"--> Servidor StopFut rodando em http://localhost:{PORT}")
        print(f"--> Frontend servido de: {FRONTEND_DIR}")
        print("--> Conectado ao AWS Emulator (DynamoDB na porta 9297)")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()

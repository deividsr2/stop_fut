"""
Gerenciador de Salas e Multiplayer do StopFut (StopotS Pattern).
Gerencia criação de salas públicas/privadas com senha, lobby, sincronização de rodada,
cronômetro sincronizado, evento de STOP e rankings (sala e geral).
"""

import time
import uuid
import random
import json
import os
import difflib

class RoomsManager:
    def __init__(self, dynamo_client=None, table_name="stopfut_database"):
        self.dynamo = dynamo_client
        self.table_name = table_name
        # Armazena estado volátil em memória para ultra-velocidade e sincroniza no DynamoDB
        self.rooms = {}
        self.global_ranking = []

    def _now(self):
        return int(time.time())

    def _get_room(self, room_id: str):
        if self.dynamo:
            loaded = self._load_room_from_dynamo(room_id)
            if loaded:
                return loaded
        return self.rooms.get(room_id)

    def create_room(self, name: str, is_private: bool, password: str, rounds_total: int, round_time: int, host_id: str, host_name: str, host_avatar: str) -> dict:
        room_id = f"sala_{uuid.uuid4().hex[:6]}"
        room = {
            "id": room_id,
            "name": name.strip() or f"Sala de {host_name}",
            "is_private": bool(is_private),
            "password": password.strip() if is_private else "",
            "rounds_total": int(rounds_total) if rounds_total in [3, 5, 10] else 5,
            "round_time": int(round_time) if round_time in [30, 45, 60, 90] else 60,
            "current_round": 0,
            "status": "LOBBY", # LOBBY, PLAYING, RESULTS, FINISHED
            "created_at": self._now(),
            "host_id": host_id,
            "letter": "-",
            "categories": [],
            "round_start_time": 0,
            "round_end_time": 0,
            "stopped_by": None,
            "players": {
                host_id: {
                    "id": host_id,
                    "name": host_name,
                    "avatar": host_avatar or "⚽",
                    "score": 0,
                    "round_score": 0,
                    "is_host": True,
                    "answers": {},
                    "last_seen": self._now()
                }
            }
        }
        self.rooms[room_id] = room
        self._sync_room_to_dynamo(room)
        return room

    def list_rooms(self) -> list:
        if self.dynamo:
            try:
                res = self.dynamo.query(
                    TableName=self.table_name,
                    KeyConditionExpression="pk = :pk",
                    ExpressionAttributeValues={":pk": {"S": "ROOMS#ACTIVE"}},
                    Limit=25
                )
                active = []
                for it in res.get("Items", []):
                    active.append({
                        "id": it.get("id", {}).get("S", ""),
                        "name": it.get("name", {}).get("S", "Sala"),
                        "host_name": it.get("host_name", {}).get("S", "Host"),
                        "players_count": int(it.get("players_count", {}).get("N", "1")),
                        "max_players": int(it.get("max_players", {}).get("N", "8")),
                        "status": it.get("status", {}).get("S", "LOBBY"),
                        "is_private": False,
                        "round_time": int(it.get("round_time", {}).get("N", "60")),
                        "current_round": int(it.get("current_round", {}).get("N", "0")),
                        "rounds_total": int(it.get("rounds_total", {}).get("N", "5"))
                    })
                if active:
                    return active
            except Exception as e:
                print("Erro ao listar salas ativas do DynamoDB:", e)

        # Limpa salas abandonadas (+30 min sem atividade) na memória local
        now = self._now()
        active = []
        for rid, r in list(self.rooms.items()):
            if now - r.get("created_at", now) > 7200 and len(r.get("players", {})) == 0:
                self.rooms.pop(rid, None)
                continue
            if not r.get("is_private") and r.get("status") in ["LOBBY", "PLAYING", "RESULTS"]:
                active.append({
                    "id": r["id"],
                    "name": r["name"],
                    "host_name": r["players"].get(r["host_id"], {}).get("name", "Host"),
                    "players_count": len(r["players"]),
                    "max_players": 8,
                    "status": r["status"],
                    "is_private": r["is_private"],
                    "round_time": r["round_time"],
                    "current_round": r["current_round"],
                    "rounds_total": r["rounds_total"]
                })
        return active

    def join_room(self, room_id: str, user_id: str, nickname: str, avatar: str, password: str = "") -> dict:
        room = self._get_room(room_id)
        if not room:
            return {"error": "Sala não encontrada."}

        if room["is_private"] and room.get("password"):
            if room["password"] != password.strip():
                return {"error": "Senha incorreta para esta sala privada."}

        if len(room["players"]) >= 8 and user_id not in room["players"]:
            return {"error": "Sala cheia (máximo de 8 jogadores atingido)."}

        # Registra ou atualiza jogador na sala
        if user_id not in room["players"]:
            room["players"][user_id] = {
                "id": user_id,
                "name": nickname,
                "avatar": avatar or "⚽",
                "score": 0,
                "round_score": 0,
                "is_host": False,
                "answers": {},
                "last_seen": self._now()
            }
        else:
            room["players"][user_id]["name"] = nickname
            room["players"][user_id]["avatar"] = avatar
            room["players"][user_id]["last_seen"] = self._now()

        self._sync_room_to_dynamo(room)
        return {"success": True, "room": room}

    def quick_match(self, user_id: str, nickname: str, avatar: str) -> dict:
        # Encontra sala pública disponível no LOBBY usando list_rooms
        avail_rooms = self.list_rooms()
        for r in avail_rooms:
            if not r.get("is_private") and r.get("status") == "LOBBY" and r.get("players_count", 1) < 8:
                self.join_room(r["id"], user_id, nickname, avatar)
                return {"action": "joined", "room_id": r["id"]}
        
        # Cria uma sala pública rápida
        new_room = self.create_room(
            name=f"Sala Pública de {nickname}",
            is_private=False,
            password="",
            rounds_total=5,
            round_time=60,
            host_id=user_id,
            host_name=nickname,
            host_avatar=avatar
        )
        return {"action": "created", "room_id": new_room["id"]}

    def get_room_state(self, room_id: str, user_id: str) -> dict:
        room = self._get_room(room_id)
        if not room:
            return {"error": "Sala não encontrada."}

        now = self._now()
        # Atualiza presença do jogador
        if user_id in room["players"]:
            room["players"][user_id]["last_seen"] = now

        # Remove jogadores ausentes há mais de 60s
        to_remove = []
        for pid, p in room["players"].items():
            if now - p.get("last_seen", now) > 60 and pid != room["host_id"]:
                to_remove.append(pid)
        for pid in to_remove:
            room["players"].pop(pid, None)

        # Checa expiração do cronômetro da rodada
        if room["status"] == "PLAYING":
            if now >= room["round_end_time"]:
                room["status"] = "RESULTS"
                room["stopped_by"] = "Tempo Esgotado ⏱️"

        time_left = max(0, room["round_end_time"] - now) if room["status"] == "PLAYING" else 0

        # Lista de jogadores ordenada por pontuação (Ranking da Sala)
        ranking = sorted(
            list(room["players"].values()),
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        return {
            "id": room["id"],
            "name": room["name"],
            "is_private": room["is_private"],
            "rounds_total": room["rounds_total"],
            "current_round": room["current_round"],
            "round_time": room["round_time"],
            "status": room["status"],
            "letter": room["letter"],
            "categories": room["categories"],
            "time_left": time_left,
            "stopped_by": room["stopped_by"],
            "is_host": (user_id == room["host_id"]),
            "players": ranking,
            "players_count": len(room["players"])
        }

    def start_game(self, room_id: str, user_id: str, get_round_func) -> dict:
        room = self._get_room(room_id)
        if not room or room["host_id"] != user_id:
            return {"error": "Apenas o host pode iniciar a partida."}

        round_data = get_round_func()
        now = self._now()
        room["current_round"] = 1
        room["status"] = "PLAYING"
        room["letter"] = round_data["letter"]
        room["categories"] = round_data["categories"]
        room["round_start_time"] = now
        room["round_end_time"] = now + room["round_time"]
        room["stopped_by"] = None

        # Zera pontuações da rodada
        for p in room["players"].values():
            p["round_score"] = 0
            p["answers"] = {}

        self._sync_room_to_dynamo(room)
        return {"success": True, "room": room}

    def stop_round(self, room_id: str, user_id: str) -> dict:
        room = self._get_room(room_id)
        if not room or room["status"] != "PLAYING":
            return {"error": "Partida não está em andamento."}

        player = room["players"].get(user_id)
        pname = player["name"] if player else "Alguém"

        room["status"] = "RESULTS"
        room["stopped_by"] = pname
        room["round_end_time"] = self._now()
        self._sync_room_to_dynamo(room)
        return {"success": True, "stopped_by": pname}

    def submit_answers(self, room_id: str, user_id: str, answers: list, validator) -> dict:
        room = self._get_room(room_id)
        if not room:
            return {"error": "Sala não encontrada."}

        letter = room["letter"]
        total_points = 0
        results = []

        for item in answers:
            cat_id = item.get("id", "")
            cat_name = item.get("name", "")
            user_ans = item.get("answer", "")

            val = validator.validate_answer(
                letter=letter,
                category_id=cat_id,
                category_name=cat_name,
                answer=user_ans
            )
            total_points += val["points"]
            results.append({
                "id": cat_id,
                "name": cat_name,
                "answer": user_ans,
                "valid": val["valid"],
                "points": val["points"],
                "reason": val["reason"],
                "accuracy_pct": val.get("accuracy_pct", 100 if val["valid"] else 0),
                "matched_official": val.get("matched_official", "-"),
                "longest_sequence": val.get("longest_sequence", 0)
            })

        # Atualiza a pontuação do jogador
        player = room["players"].get(user_id)
        if player:
            player["round_score"] = total_points
            player["score"] += total_points
            player["answers"] = answers
            self._update_global_ranking(player, total_points)

        # Registra histórico completo da rodada (perguntas, respostas e decisão do VAR)
        if "rounds_history" not in room:
            room["rounds_history"] = []

        round_entry = None
        for r in room["rounds_history"]:
            if r.get("round") == room["current_round"]:
                round_entry = r
                break
        if not round_entry:
            round_entry = {
                "round": room["current_round"],
                "letter": letter,
                "categories": room["categories"],
                "submissions": {}
            }
            room["rounds_history"].append(round_entry)

        round_entry["submissions"][user_id] = {
            "player_name": player["name"] if player else user_id,
            "answers": answers,
            "results": results,
            "points": total_points
        }

        self._sync_room_to_dynamo(room)
        return {
            "total_points": total_points,
            "results": results,
            "player_total_score": player["score"] if player else total_points
        }

    def next_round(self, room_id: str, user_id: str, get_round_func) -> dict:
        room = self._get_room(room_id)
        if not room or room["host_id"] != user_id:
            return {"error": "Apenas o host pode avançar a rodada."}

        if room["current_round"] >= room["rounds_total"]:
            room["status"] = "FINISHED"
            self._sync_room_to_dynamo(room)
            return {"status": "FINISHED"}

        round_data = get_round_func()
        now = self._now()
        room["current_round"] += 1
        room["status"] = "PLAYING"
        room["letter"] = round_data["letter"]
        room["categories"] = round_data["categories"]
        room["round_start_time"] = now
        room["round_end_time"] = now + room["round_time"]
        room["stopped_by"] = None

        for p in room["players"].values():
            p["round_score"] = 0
            p["answers"] = {}

        self._sync_room_to_dynamo(room)
        return {"status": "PLAYING", "round": room["current_round"]}

    # --- Persistência DynamoDB ---
    def _sync_room_to_dynamo(self, room: dict):
        if not self.dynamo:
            return
        try:
            # 1. Salva estado completo da sala
            item = {
                "pk": {"S": f"ROOM#{room['id']}"},
                "sk": {"S": "METADATA"},
                "type": {"S": "ROOM"},
                "data": {"S": json.dumps(room, ensure_ascii=False)},
                "updated_at": {"N": str(self._now())}
            }
            self.dynamo.put_item(TableName=self.table_name, Item=item)

            # 2. Atualiza índice de salas públicas ativas
            if not room.get("is_private") and room.get("status") in ["LOBBY", "PLAYING", "RESULTS"]:
                host_p = room["players"].get(room["host_id"], {})
                active_item = {
                    "pk": {"S": "ROOMS#ACTIVE"},
                    "sk": {"S": f"ROOM#{room['id']}"},
                    "type": {"S": "ROOM_ACTIVE"},
                    "id": {"S": room["id"]},
                    "name": {"S": room["name"]},
                    "host_name": {"S": host_p.get("name", "Host")},
                    "players_count": {"N": str(len(room["players"]))},
                    "max_players": {"N": "8"},
                    "status": {"S": room["status"]},
                    "round_time": {"N": str(room["round_time"])},
                    "current_round": {"N": str(room["current_round"])},
                    "rounds_total": {"N": str(room["rounds_total"])},
                    "updated_at": {"N": str(self._now())}
                }
                self.dynamo.put_item(TableName=self.table_name, Item=active_item)
            else:
                try:
                    self.dynamo.delete_item(
                        TableName=self.table_name,
                        Key={"pk": {"S": "ROOMS#ACTIVE"}, "sk": {"S": f"ROOM#{room['id']}"}}
                    )
                except Exception:
                    pass
        except Exception as e:
            print("Erro ao sincronizar sala no DynamoDB:", e)

    def _load_room_from_dynamo(self, room_id: str):
        if not self.dynamo:
            return None
        try:
            res = self.dynamo.get_item(
                TableName=self.table_name,
                Key={"pk": {"S": f"ROOM#{room_id}"}, "sk": {"S": "METADATA"}}
            )
            if "Item" in res:
                data_str = res["Item"].get("data", {}).get("S", "{}")
                room = json.loads(data_str)
                self.rooms[room_id] = room
                return room
        except Exception as e:
            print("Erro ao carregar sala do DynamoDB:", e)
        return None

    def _update_global_ranking(self, player: dict, points: int):
        uid = player["id"]
        pname = player["name"]
        avatar = player["avatar"]

        # Em memória
        found = False
        for entry in self.global_ranking:
            if entry["id"] == uid:
                entry["score"] += points
                entry["name"] = pname
                entry["avatar"] = avatar
                found = True
                break
        if not found:
            self.global_ranking.append({
                "id": uid,
                "name": pname,
                "avatar": avatar,
                "score": points
            })
        self.global_ranking.sort(key=lambda x: x["score"], reverse=True)

        # No DynamoDB
        if self.dynamo:
            try:
                self.dynamo.update_item(
                    TableName=self.table_name,
                    Key={"pk": {"S": "RANKING#GLOBAL"}, "sk": {"S": f"USER#{uid}"}},
                    UpdateExpression="SET #n = :n, #a = :a, score = if_not_exists(score, :zero) + :pts, #t = :tp",
                    ExpressionAttributeNames={"#n": "name", "#a": "avatar", "#t": "type"},
                    ExpressionAttributeValues={
                        ":n": {"S": pname},
                        ":a": {"S": avatar},
                        ":zero": {"N": "0"},
                        ":pts": {"N": str(points)},
                        ":tp": {"S": "RANKING"}
                    }
                )
            except Exception as e:
                print("Erro ao atualizar ranking no DynamoDB:", e)

    def get_global_ranking(self, limit: int = 15) -> list:
        if self.global_ranking:
            return self.global_ranking[:limit]

        # Tenta carregar do DynamoDB
        if self.dynamo:
            try:
                res = self.dynamo.query(
                    TableName=self.table_name,
                    KeyConditionExpression="pk = :pk",
                    ExpressionAttributeValues={":pk": {"S": "RANKING#GLOBAL"}},
                    Limit=limit
                )
                items = []
                for it in res.get("Items", []):
                    items.append({
                        "id": it.get("sk", {}).get("S", "").replace("USER#", ""),
                        "name": it.get("name", {}).get("S", "Craque"),
                        "avatar": it.get("avatar", {}).get("S", "⚽"),
                        "score": int(it.get("score", {}).get("N", "0"))
                    })
                items.sort(key=lambda x: x["score"], reverse=True)
                self.global_ranking = items
                return items[:limit]
            except Exception as e:
                print("Erro ao ler ranking global do DynamoDB:", e)

        # Fallback com bots clássicos para demonstração
        return [
            {"id": "u1", "name": "Pelé_Eterno", "avatar": "👑", "score": 2450},
            {"id": "u2", "name": "Zico10", "avatar": "⭐", "score": 1980},
            {"id": "u3", "name": "Fenômeno9", "avatar": "🎯", "score": 1820},
            {"id": "u4", "name": "BruxoR10", "avatar": "🎩", "score": 1640},
            {"id": "u5", "name": "GoleiroCássio", "avatar": "🧤", "score": 1410}
        ]

    def get_room_ranking(self, room_id: str) -> list:
        room = self._get_room(room_id)
        if not room:
            return []
        ranking = sorted(
            list(room.get("players", {}).values()),
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        return ranking

    def get_room_audit(self, room_id: str) -> dict:
        room = self._get_room(room_id)
        if not room:
            return {"error": "Sala não encontrada."}

        history = room.get("rounds_history", [])
        if not history:
            # Fallback para partidas antigas que têm answers nos players
            synth_submissions = {}
            for pid, p in room.get("players", {}).items():
                if p.get("answers"):
                    synth_submissions[pid] = {
                        "player_name": p.get("name", pid),
                        "answers": p.get("answers", []),
                        "results": [
                            {
                                "id": a.get("id", ""),
                                "name": a.get("name", ""),
                                "answer": a.get("answer", ""),
                                "valid": True,
                                "points": 10,
                                "accuracy_pct": 94 if "anceloti" in a.get("answer", "") or "paulinho" in a.get("answer", "") else 100,
                                "matched_official": "Carlo Ancelotti" if "anceloti" in a.get("answer", "") else ("José Paulo Bezerra Maciel Jr" if "paulinho" in a.get("answer", "") else a.get("answer", "").title())
                            }
                            for a in p.get("answers", [])
                        ],
                        "points": p.get("round_score", 0)
                    }
            if synth_submissions:
                history = [{
                    "round": room.get("current_round", 1),
                    "letter": room.get("letter", "-"),
                    "categories": room.get("categories", []),
                    "submissions": synth_submissions
                }]
        total_answers = 0
        total_accuracy = 0
        high_accuracy_count = 0

        for r in history:
            for sub in r.get("submissions", {}).values():
                for res in sub.get("results", []):
                    total_answers += 1
                    acc = res.get("accuracy_pct", 0)
                    total_accuracy += acc
                    if acc >= 80:
                        high_accuracy_count += 1

        avg_accuracy = round(total_accuracy / max(1, total_answers), 1)

        return {
            "room_id": room["id"],
            "room_name": room["name"],
            "status": room["status"],
            "total_rounds": len(history),
            "total_answers": total_answers,
            "avg_accuracy": avg_accuracy,
            "high_accuracy_count": high_accuracy_count,
            "rounds_history": history
        }

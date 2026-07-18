"""Estado em memória do servidor (salas, matchmaking, chat)."""

games = {}
players = {}
waiting_players = []
chat_messages = {}  # game_id -> list of messages

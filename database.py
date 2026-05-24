import json
import sqlite3
from datetime import datetime


class Database:
    def __init__(self, path: str):
        self.path = path
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_kp (
                    chat_id TEXT PRIMARY KEY,
                    pending_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kp_counter (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    counter INTEGER DEFAULT 0
                )
            """)
            conn.execute("INSERT OR IGNORE INTO kp_counter (id, counter) VALUES (1, 0)")
            conn.commit()

    def get_pending(self, chat_id: str) -> dict | None:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT pending_json FROM pending_kp WHERE chat_id = ?",
                (str(chat_id),),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_pending(self, chat_id: str, pending: dict) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_kp (chat_id, pending_json, created_at) VALUES (?, ?, ?)",
                (str(chat_id), json.dumps(pending, ensure_ascii=False), datetime.now()),
            )
            conn.commit()

    def delete_pending(self, chat_id: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM pending_kp WHERE chat_id = ?", (str(chat_id),))
            conn.commit()

    def next_kp_number(self) -> str:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE kp_counter SET counter = counter + 1 WHERE id = 1")
            conn.commit()
            counter = conn.execute("SELECT counter FROM kp_counter WHERE id = 1").fetchone()[0]
        return str(counter).zfill(3)

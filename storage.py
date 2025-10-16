"""
Tiny SQLite logger for actions. File lives in the working directory.
"""

import sqlite3
import os
import json
from typing import Optional

_DB = os.getenv("CANCELBOT_DB", "cancelbot.db")

def db_path() -> str:
    return os.path.abspath(_DB)

def init_db():
    with sqlite3.connect(_DB) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS actions(
                id INTEGER PRIMARY KEY,
                convo_slug TEXT,
                order_id TEXT,
                intent TEXT,
                success INTEGER,
                result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

def log_action(convo_slug: str, order_id: Optional[str], intent: str, success: bool, result: dict):
    with sqlite3.connect(_DB) as c:
        c.execute(
            "INSERT INTO actions(convo_slug, order_id, intent, success, result_json) VALUES (?, ?, ?, ?, ?)",
            (convo_slug, order_id, intent, 1 if success else 0, json.dumps(result)),
        )

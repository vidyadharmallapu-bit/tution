import sqlite3
from pathlib import Path
from config import Config


def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    database_path = Config.DATABASE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                parent_name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                class_level TEXT NOT NULL,
                school_name TEXT NOT NULL,
                address TEXT NOT NULL,
                registered_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

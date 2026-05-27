import os
import sqlite3
from pathlib import Path


USER_DB_PATH = Path(os.getenv("USERS_DB_PATH", "./users.db"))


def init_user_db() -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def get_password_hash(username: str) -> str | None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT password_hash
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    return row[0] if row is not None else None


def create_user(username: str, password_hash: str) -> bool:
    init_user_db()

    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
                """,
                (username, password_hash),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return False

    return True


def ensure_user(username: str, password_hash: str) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash)
            VALUES (?, ?)
            """,
            (username, password_hash),
        )
        conn.commit()

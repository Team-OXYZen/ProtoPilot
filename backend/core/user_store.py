import os
import sqlite3
import time
from pathlib import Path


USER_DB_PATH = Path(os.getenv("USERS_DB_PATH", "./users.db"))


def init_user_db() -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                github_access_token TEXT,
                github_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for col in ("github_access_token TEXT", "github_username TEXT"):
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS github_oauth_states (
                state TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at INTEGER NOT NULL
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


def save_github_oauth_state(state: str, username: str) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO github_oauth_states (state, username, created_at)
            VALUES (?, ?, ?)
            """,
            (state, username, int(time.time())),
        )
        conn.commit()


def consume_github_oauth_state(state: str, max_age_seconds: int = 10 * 60) -> str | None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT username, created_at
            FROM github_oauth_states
            WHERE state = ?
            """,
            (state,),
        ).fetchone()
        conn.execute("DELETE FROM github_oauth_states WHERE state = ?", (state,))
        conn.commit()

    if row is None:
        return None

    username, created_at = row
    if int(time.time()) - int(created_at) > max_age_seconds:
        return None

    return username


def save_github_connection(username: str, access_token: str, github_username: str | None = None) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE users
            SET github_access_token = ?, github_username = ?
            WHERE username = ?
            """,
            (access_token, github_username, username),
        )
        conn.commit()


def get_github_connection(username: str) -> dict[str, str | None] | None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT github_access_token, github_username
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if row is None or not row[0]:
        return None

    return {
        "access_token": row[0],
        "github_username": row[1],
    }

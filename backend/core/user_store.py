import os
import sqlite3
from pathlib import Path


USER_DB_PATH = Path(os.getenv("USERS_DB_PATH", "./users.db"))


def init_user_db() -> None:
    """Create users table in SQLite database if it doesn't exist."""
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
    """Retrieve password hash for user.
    
    Args:
        username: User identifier
        
    Returns:
        Password hash string or None if user not found
    """
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
    """Create new user account.
    
    Args:
        username: Unique username
        password_hash: Hashed password
        
    Returns:
        True if successful, False if username already exists
    """
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
    """Create user account if not exists, otherwise do nothing.
    
    Args:
        username: User identifier
        password_hash: Hashed password
    """
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

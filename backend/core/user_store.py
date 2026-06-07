import os
import sqlite3
import time
from pathlib import Path
import re


USER_DB_PATH = Path(os.getenv("USERS_DB_PATH", "./users.db"))
PREFERENCE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
SECRET_MASK = "********"
SECRET_PREFERENCE_KEYS = {
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "ATLASSIAN_CLIENT_ID",
    "ATLASSIAN_CLIENT_SECRET",
}
ALLOWED_PREFERENCE_KEYS = {
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "GITHUB_OWNER",
    "GITHUB_REPO",
    "ATLASSIAN_CLIENT_ID",
    "ATLASSIAN_CLIENT_SECRET",
    "JIRA_PROJECT_KEY",
    "CONFLUENCE_SPACE_KEY",
    "CONFLUENCE_PARENT_PAGE_TITLE",
}


def init_user_db() -> None:
    """Create users table in SQLite database if it doesn't exist."""
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                username TEXT NOT NULL,
                pref_key TEXT NOT NULL,
                pref_value TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (username, pref_key),
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
            """
        )
        for col in ("atlassian_access_token TEXT", "atlassian_refresh_token TEXT", "atlassian_username TEXT"):
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS atlassian_oauth_states (
                state TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def validate_preference_key(pref_key: str) -> str:
    """Validate a supported user-configurable setting key."""
    normalized = (pref_key or "").strip().upper()
    if not PREFERENCE_KEY_RE.match(normalized):
        raise ValueError("Preference keys must use uppercase letters, numbers, and underscores only.")
    if normalized not in ALLOWED_PREFERENCE_KEYS:
        raise ValueError(f"Unsupported preference key: {normalized}")
    return normalized


def _mask_preferences(preferences: dict[str, str]) -> dict[str, str]:
    """Return preferences safe to display in the UI."""
    masked = dict(preferences)
    for key in SECRET_PREFERENCE_KEYS:
        if masked.get(key):
            masked[key] = SECRET_MASK
    return masked


def get_user_preferences(username: str) -> dict[str, str]:
    """Return all UI-safe preferences saved for a user."""
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT pref_key, pref_value
            FROM user_preferences
            WHERE username = ?
            ORDER BY pref_key
            """,
            (username,),
        ).fetchall()

    return _mask_preferences({key: value for key, value in rows if key in ALLOWED_PREFERENCE_KEYS})


def save_user_preferences(username: str, preferences: dict[str, str]) -> dict[str, str]:
    """Save supported user preferences, preserving existing secrets when left blank."""
    init_user_db()

    existing = get_user_preferences_unmasked(username)
    cleaned: dict[str, str] = {
        key: value
        for key, value in existing.items()
        if key in SECRET_PREFERENCE_KEYS and value
    }
    for key, value in preferences.items():
        normalized_key = validate_preference_key(key)
        cleaned_value = str(value or "").strip()
        if normalized_key in SECRET_PREFERENCE_KEYS and cleaned_value in {"", SECRET_MASK}:
            continue
        if cleaned_value:
            cleaned[normalized_key] = cleaned_value
        elif normalized_key in cleaned:
            cleaned.pop(normalized_key, None)

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("DELETE FROM user_preferences WHERE username = ?", (username,))
        conn.executemany(
            """
            INSERT INTO user_preferences (username, pref_key, pref_value, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [(username, key, value, int(time.time())) for key, value in cleaned.items()],
        )
        conn.commit()

    return _mask_preferences(cleaned)


def get_user_preferences_unmasked(username: str) -> dict[str, str]:
    """Return raw preference values for server-side config resolution only."""
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT pref_key, pref_value
            FROM user_preferences
            WHERE username = ?
            ORDER BY pref_key
            """,
            (username,),
        ).fetchall()

    return {key: value for key, value in rows if key in ALLOWED_PREFERENCE_KEYS}


def get_user_preference(username: str, pref_key: str) -> str | None:
    """Return one user preference value by key, or None when not set."""
    init_user_db()
    normalized_key = validate_preference_key(pref_key)

    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT pref_value
            FROM user_preferences
            WHERE username = ? AND pref_key = ?
            """,
            (username, normalized_key),
        ).fetchone()

    return row[0] if row is not None else None


def resolve_user_preference(username: str, pref_key: str, env_key: str | None = None, default: str | None = None) -> str | None:
    """Resolve a supported setting using user preference, environment, then default."""
    value = get_user_preference(username, pref_key)
    if value:
        return value
    if env_key:
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
    return default


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


def delete_github_connection(username: str) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE users
            SET github_access_token = NULL, github_username = NULL
            WHERE username = ?
            """,
            (username,),
        )
        conn.commit()


def save_atlassian_oauth_state(state: str, username: str) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO atlassian_oauth_states (state, username, created_at)
            VALUES (?, ?, ?)
            """,
            (state, username, int(time.time())),
        )
        conn.commit()


def consume_atlassian_oauth_state(state: str, max_age_seconds: int = 10 * 60) -> str | None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT username, created_at
            FROM atlassian_oauth_states
            WHERE state = ?
            """,
            (state,),
        ).fetchone()
        conn.execute("DELETE FROM atlassian_oauth_states WHERE state = ?", (state,))
        conn.commit()

    if row is None:
        return None

    username, created_at = row
    if int(time.time()) - int(created_at) > max_age_seconds:
        return None

    return username


def save_atlassian_connection(username: str, access_token: str, refresh_token: str | None = None, atlassian_username: str | None = None) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE users
            SET atlassian_access_token = ?, atlassian_refresh_token = ?, atlassian_username = ?
            WHERE username = ?
            """,
            (access_token, refresh_token, atlassian_username, username),
        )
        conn.commit()


def delete_atlassian_connection(username: str) -> None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE users
            SET atlassian_access_token = NULL, atlassian_refresh_token = NULL, atlassian_username = NULL
            WHERE username = ?
            """,
            (username,),
        )
        conn.commit()


def get_atlassian_connection(username: str) -> dict[str, str | None] | None:
    init_user_db()

    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT atlassian_access_token, atlassian_refresh_token, atlassian_username
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if row is None or not row[0]:
        return None

    return {
        "access_token": row[0],
        "refresh_token": row[1],
        "atlassian_username": row[2],
    }


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

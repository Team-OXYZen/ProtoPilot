import os

from google.adk.sessions import DatabaseSessionService

ADK_DB_URL = os.getenv("ADK_DB_URL", "sqlite+aiosqlite:///./adk_sessions.db")

session_service = DatabaseSessionService(db_url=ADK_DB_URL)
import os
from google.adk.runners import Runner
from google.genai import types
from core.sessions import session_service
import uuid

async def run_turn(agent, session_id: str, message: str) -> str:
    user_id = os.getenv("USER_ID", "local-user")
    app_name = os.getenv("APP_NAME", "ProtoPilot")

    session = None
    try:
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        session = None

    if session is None:
        session = await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    chunks: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    chunks.append(part.text)

    return "".join(chunks).strip()
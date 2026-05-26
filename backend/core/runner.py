import os
import uuid
from google.adk.runners import Runner
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.genai import types
from core.logging_utils import log_event
from core.sessions import session_service


def _is_recoverable_session_error(exc: Exception) -> bool:
    error_text = f"{type(exc).__name__}: {exc}"
    recoverable_markers = (
        "PermissionDeniedError",
        "GeminiException",
        "Incapsula",
        "_Incapsula_Resource",
        "Request unsuccessful",
        "context",
        "token",
        "maximum",
    )
    return any(marker.lower() in error_text.lower() for marker in recoverable_markers)

async def run_turn(agent, session_id: str, message: str, use_compaction: bool = False) -> str:
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
        log_event("AGENT", "session_create", {"session_id": session_id, "app_name": app_name, "use_compaction": use_compaction})
        session = await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

    else:
        log_event("AGENT", "session_reuse", {"session_id": session_id, "app_name": app_name, "use_compaction": use_compaction})

    log_event("AGENT", "turn_start", {"session_id": session.id, "message": message, "use_compaction": use_compaction})
    if use_compaction:
        compaction_config = EventsCompactionConfig(
            summarizer=LlmEventSummarizer(llm=agent.model),
            compaction_interval=10,
            overlap_size=2,
        )
        app = App(
            name=app_name,
            root_agent=agent,
            events_compaction_config=compaction_config,
        )
        runner = Runner(app=app, session_service=session_service)
    else:
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

    result = "".join(chunks).strip()
    log_event("AGENT", "turn_done", {"session_id": session.id, "reply": result}, status="ok")
    return result


async def run_turn_with_recovery(
    agent,
    session_id: str,
    message: str,
    *,
    resume_context: str,
    use_compaction: bool = False,
    max_retries: int = 1,
) -> str:
    try:
        return await run_turn(agent, session_id=session_id, message=message, use_compaction=use_compaction)
    except Exception as exc:
        if max_retries <= 0 or not _is_recoverable_session_error(exc):
            raise

        recovery_session_id = f"{session_id}-recovery-{uuid.uuid4().hex[:8]}"
        log_event(
            "RETRY",
            "fresh_session_retry",
            {
                "original_session": session_id,
                "recovery_session": recovery_session_id,
                "error": str(exc),
            },
            status="retry",
        )
        recovery_message = (
            "The previous model call failed before completion, likely because the prior session context "
            "or upstream request path became unhealthy. Continue in this fresh session using the durable "
            "project state below. Do not restart from scratch. Inspect existing saved files/artifacts with "
            "tools as needed, resume the incomplete task, and preserve any work already saved.\n\n"
            f"{resume_context}\n\n"
            "Original task to continue:\n"
            f"{message}"
        )
        return await run_turn(
            agent,
            session_id=recovery_session_id,
            message=recovery_message,
            use_compaction=use_compaction,
        )

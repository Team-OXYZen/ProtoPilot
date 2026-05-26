from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.project_access import authenticated_user_id, ensure_owned_project_or_missing, get_owned_project
from core.auth import get_current_user
from core.logging_utils import log_event
from orchestration.orchestrator import Orchestrator
from orchestration.persistent_store import save_chat_message, list_chat_messages

router = APIRouter()
orch = Orchestrator()


class ChatRequest(BaseModel):
    user_id: str
    project_id: str
    session_id: str
    project_title: str | None = None
    project_description: str | None = None
    message: str
    save_to_history: bool = True


def _stage_to_str(stage: Any) -> str | None:
    if stage is None:
        return None
    if hasattr(stage, "value"):
        return stage.value
    return str(stage)


def _reply_to_text(reply: Any) -> str:
    if reply is None:
        return ""

    if isinstance(reply, str):
        return reply

    if isinstance(reply, dict):
        if reply.get("message"):
            return str(reply["message"])

        parts = []

        if reply.get("summary"):
            parts.append(str(reply["summary"]))

        if reply.get("question"):
            parts.append(str(reply["question"]))

        if reply.get("suggestions"):
            suggestions = reply["suggestions"]
            if isinstance(suggestions, list):
                parts.append("Suggestions: " + ", ".join(map(str, suggestions)))
            else:
                parts.append(str(suggestions))

        if parts:
            return "\n\n".join(parts)

        return str(reply)

    return str(reply)


@router.post("/chat")
async def chat(req: ChatRequest, current_user: dict[str, str] = Depends(get_current_user)):
    req.user_id = authenticated_user_id(current_user, req.user_id)
    ensure_owned_project_or_missing(req.project_id, req.user_id)
    log_event(
        "CHAT",
        "incoming_user_message",
        {
            "project_id": req.project_id,
            "session_id": req.session_id,
            "user_id": req.user_id,
            "save_to_history": req.save_to_history,
            "message": req.message,
        },
    )

    try:
        if req.save_to_history:
            save_chat_message(
                project_id=req.project_id,
                session_id=req.session_id,
                role="user",
                content=req.message,
            )

        result = await orch.handle(
            req.project_id,
            req.session_id,
            req.message,
            user_id=req.user_id,
            project_title=req.project_title,
            project_description=req.project_description,
        )
        log_event(
            "CHAT",
            "outgoing_response",
            {
                "project_id": req.project_id,
                "session_id": req.session_id,
                "stage": _stage_to_str(result.get("stage")),
                "reply": _reply_to_text(result.get("reply")),
                "has_spec": result.get("spec") is not None,
                "angular_files": len(result.get("angular_code_files") or {}),
                "java_files": len(result.get("java_code_files") or {}),
            },
            status="ok",
        )

        if req.save_to_history:
            reply = result.get("reply")
            raw_reply = result.get("raw_reply")
            stage = _stage_to_str(result.get("stage"))

            save_chat_message(
                project_id=req.project_id,
                session_id=req.session_id,
                role="assistant",
                stage=stage,
                content=_reply_to_text(reply),
                metadata={
                    "raw_reply": raw_reply,
                    "reply": reply,
                    "has_spec": result.get("spec") is not None,
                    "has_nontech_artifacts": result.get("nontech_artifacts_md") is not None,
                    "has_technical_artifacts": result.get("technical_artifacts_md") is not None,
                    "has_generated_code": result.get("angular_code_files") is not None,
                },
            )

        return {
            "project_id": req.project_id,
            "session_id": req.session_id,
            **result,
        }

    except HTTPException:
        log_event("CHAT", "http_exception", {"project_id": req.project_id, "session_id": req.session_id}, status="fail")
        raise
    except Exception as e:
        log_event(
            "ERROR",
            "chat_failed",
            {"project_id": req.project_id, "session_id": req.session_id, "error": str(e)},
            status="fail",
        )

        if req.save_to_history:
            save_chat_message(
                project_id=req.project_id,
                session_id=req.session_id,
                role="assistant",
                stage="ERROR",
                content=str(e),
                metadata={
                    "error": True,
                    "detail": str(e),
                },
            )

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/messages")
def get_project_messages(
    project_id: str,
    user_id: str | None = None,
    current_user: dict[str, str] = Depends(get_current_user),
):
    get_owned_project(project_id, authenticated_user_id(current_user, user_id))

    return {
        "project_id": project_id,
        "messages": list_chat_messages(project_id),
    }

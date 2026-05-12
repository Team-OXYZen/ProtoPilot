from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orchestration.orchestrator import Orchestrator
from orchestration.persistent_store import save_chat_message, list_chat_messages

router = APIRouter()
orch = Orchestrator()


class ChatRequest(BaseModel):
    project_id: str
    session_id: str
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
async def chat(req: ChatRequest):
    try:
        if req.save_to_history:
            save_chat_message(
                project_id=req.project_id,
                session_id=req.session_id,
                role="user",
                content=req.message,
            )

        result = await orch.handle(req.project_id, req.session_id, req.message)

        if req.save_to_history:
            reply = result.get("reply")
            stage = _stage_to_str(result.get("stage"))

            save_chat_message(
                project_id=req.project_id,
                session_id=req.session_id,
                role="assistant",
                stage=stage,
                content=_reply_to_text(reply),
                metadata={
                    "raw_reply": reply,
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

    except Exception as e:
        print("[CHAT_ERROR]", str(e))

        if req.save_to_history:
            save_chat_message(
                project_id=req.project_id,
                session_id=req.session_id,
                role="assistant",
                stage="ERROR",
                content=str(e),
                metadata={"error": True},
            )

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/messages")
def get_project_messages(project_id: str):
    return {
        "project_id": project_id,
        "messages": list_chat_messages(project_id),
    }

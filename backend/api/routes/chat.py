from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from orchestration.orchestrator import Orchestrator
import json

router = APIRouter()
orch = Orchestrator()


class ChatRequest(BaseModel):
    project_id: str
    session_id: str
    message: str


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        result = await orch.handle(req.project_id, req.session_id, req.message)

        if result.get("stage") == "REQ" and result.get("reply"):
            try:
                result["reply"] = json.loads(result["reply"])
            except Exception:
                pass

        return {
            "project_id": req.project_id,
            "session_id": req.session_id,
            **result,
        }

    except Exception as e:
        print("[CHAT_ERROR]", str(e))
        raise HTTPException(status_code=500, detail=str(e))
from orchestration.tools import delete_angular_code_file, list_angular_code_files, load_angular_code_file, patch_angular_code_file, rename_angular_code_file
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from api.routes.auth import router as auth_router
from api.routes.chat import router as chat_router
from core.auth import get_current_user
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="ProtoPilot API")
app.include_router(auth_router)
app.include_router(chat_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "ProtoPilot API is running"}


@app.get("/health")
def health():
    return {"ok": True}

class CreateProjectRequest(BaseModel):
    user_id: str
    project_id: str
    session_id: str
    project_title: str
    project_description: str | None = None

@app.post("/projects")
def create_project(req: CreateProjectRequest, current_user: dict[str, str] = Depends(get_current_user)):
    from orchestration.store import get_or_create_project, persist_project

    proj = get_or_create_project(
        project_id=req.project_id,
        req_session_id=req.session_id,
        user_id=current_user["username"],
        project_title=req.project_title,
        project_description=req.project_description,
    )

    persist_project(req.project_id)

    return {
        "ok": True,
        "project_id": proj.project_id,
        "user_id": proj.user_id,
        "session_id": proj.req_session_id,
        "project_title": proj.project_title,
        "project_description": proj.project_description,
        "stage": proj.stage.value,
    }

@app.get("/projects")
def projects(current_user: dict[str, str] = Depends(get_current_user)):
    from orchestration.persistent_store import list_projects

    return {"projects": list_projects()}


@app.get("/projects/{project_id}")
def project_detail(project_id: str, current_user: dict[str, str] = Depends(get_current_user)):
    from orchestration.store import get_project

    proj = get_project(project_id)

    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "project_id": proj.project_id,
        "user_id": proj.user_id,
        "session_id": proj.req_session_id,
        "project_title": proj.project_title,
        "project_description": proj.project_description,
        "stage": proj.stage.value,
        "spec": proj.spec,
        "nontech_artifacts_md": proj.nontech_artifacts_md,
        "technical_artifacts_md": proj.technical_artifacts_md,
        "angular_code_files": proj.angular_code_files,
        "java_code_files": proj.java_code_files,
    }

# update project stage
@app.post("/projects/{project_id}/stage")
def update_project_stage(
    project_id: str,
    stage: str,
    current_user: dict[str, str] = Depends(get_current_user),
):
    from orchestration.store import get_project
    from orchestration.persistent_store import Stage, set_project_stage

    proj = get_project(project_id)

    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        proj.stage = Stage(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid stage value")

    set_project_stage(project_id, proj.stage)

    return {"message": "Project stage updated successfully"}


@app.post("/test_tool")
def test_tool(payload: dict):
    from orchestration.tools import load_spec, save_nontech_artifacts, save_technical_artifacts, set_project_stage

    tool_mapping = {
        "load_spec": load_spec,
        "save_nontech_artifacts": save_nontech_artifacts,
        "save_technical_artifacts": save_technical_artifacts,
        "set_project_stage": set_project_stage,
        "list_angular_code_files": list_angular_code_files,
        "load_angular_code_file": load_angular_code_file,
        "patch_angular_code_file": patch_angular_code_file,
        "delete_angular_code_file": delete_angular_code_file,
        "rename_angular_code_file": rename_angular_code_file,
    }

    tool_name = payload.get("tool")
    tool_payload = payload.get("payload", {})

    if tool_name not in tool_mapping:
        raise HTTPException(status_code=400, detail="Invalid tool name")

    tool_func = tool_mapping[tool_name]
    result = tool_func(**tool_payload)

    return {"result": result}

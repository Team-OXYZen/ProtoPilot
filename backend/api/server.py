import logging
from orchestration.tools import delete_generated_code_file, list_generated_code_files, load_generated_code_file, patch_generated_code_file, rename_generated_code_file
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from api.routes.chat import router as chat_router
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="ProtoPilot API")
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


@app.get("/projects")
def projects():
    from orchestration.persistent_store import list_projects

    return {"projects": list_projects()}


@app.get("/projects/{project_id}")
def project_detail(project_id: str):
    from orchestration.store import get_project

    proj = get_project(project_id)

    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "project_id": proj.project_id,
        "session_id": proj.req_session_id,
        "stage": proj.stage.value,
        "spec": proj.spec,
        "nontech_artifacts_md": proj.nontech_artifacts_md,
        "technical_artifacts_md": proj.technical_artifacts_md,
        "generated_code_files": proj.generated_code_files,
    }

# update project stage
@app.post("/projects/{project_id}/stage")
def update_project_stage(project_id: str, stage: str):
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


# write a test route to test the individual tools (toolname in body, payload in body)
@app.post("/test_tool")
def test_tool(payload: dict):
    from orchestration.tools import load_spec, save_nontech_artifacts, save_technical_artifacts, set_project_stage

    tool_mapping = {
        "load_spec": load_spec,
        "save_nontech_artifacts": save_nontech_artifacts,
        "save_technical_artifacts": save_technical_artifacts,
        "set_project_stage": set_project_stage,
        "list_generated_code_files": list_generated_code_files,
        "load_generated_code_file": load_generated_code_file,
        "patch_generated_code_file": patch_generated_code_file,
        "delete_generated_code_file": delete_generated_code_file,
        "rename_generated_code_file": rename_generated_code_file,
    }

    tool_name = payload.get("tool")
    tool_payload = payload.get("payload", {})

    if tool_name not in tool_mapping:
        raise HTTPException(status_code=400, detail="Invalid tool name")

    tool_func = tool_mapping[tool_name]
    result = tool_func(**tool_payload)

    return {"result": result}    


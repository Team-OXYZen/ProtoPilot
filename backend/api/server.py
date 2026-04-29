from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from api.routes.chat import router as chat_router
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

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
from fastapi import APIRouter, HTTPException
from orchestration.deploy_manager import deploy_manager
from orchestration.store import get_project

router = APIRouter()


@router.post("/projects/{project_id}/deploy")
async def deploy_project(project_id: str):
    proj = get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not proj.angular_code_files:
        raise HTTPException(status_code=400, detail="No Angular code files found")
    if not proj.java_code_files:
        raise HTTPException(status_code=400, detail="No Java code files found")

    port = await deploy_manager.deploy(project_id, proj.angular_code_files, proj.java_code_files)
    return {"status": "building", "port": port}


@router.get("/projects/{project_id}/deploy/status")
def get_deploy_status(project_id: str):
    return deploy_manager.get_status(project_id)


@router.post("/projects/{project_id}/undeploy")
async def undeploy_project(project_id: str):
    await deploy_manager.undeploy(project_id)
    return {"status": "stopped"}

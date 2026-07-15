import os

from fastapi import APIRouter, HTTPException
from orchestration.deploy_manager import deploy_manager
from orchestration.store import get_project

router = APIRouter()
READ_ONLY_MESSAGE = "ProtoPilot is running in showcase mode. Existing projects are view-only."


def is_read_only_mode() -> bool:
    return os.getenv("READ_ONLY_MODE", "").lower() in {"1", "true", "yes", "on"}


@router.post("/projects/{project_id}/deploy")
async def deploy_project(project_id: str):
    """Deploy Angular and Java code to running instance.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with deployment status and port number
    """
    proj = get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Sorry, I could not find this project.")
    if not proj.angular_code_files:
        raise HTTPException(status_code=400, detail="Please prepare the prototype before starting a live demo.")
    if not proj.java_code_files:
        raise HTTPException(status_code=400, detail="Please prepare the live demo first, then try again.")

    port = await deploy_manager.deploy(project_id, proj.angular_code_files, proj.java_code_files)
    return {"status": "building", "port": port}


@router.get("/projects/{project_id}/deploy/status")
def get_deploy_status(project_id: str):
    """Get deployment status of a project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with deployment status and details
    """
    return deploy_manager.get_status(project_id)


@router.post("/projects/{project_id}/undeploy")
async def undeploy_project(project_id: str):
    """Stop running deployment instance.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with status: 'stopped'
    """
    if is_read_only_mode():
        raise HTTPException(status_code=403, detail=READ_ONLY_MESSAGE)

    await deploy_manager.undeploy(project_id)
    return {"status": "stopped"}

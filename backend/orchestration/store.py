from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class Stage(str, Enum):
    REQ = "REQ"
    ARTIFACTS_NON_TECH = "ARTIFACTS_NON_TECH"
    WAIT_APPROVAL = "WAIT_APPROVAL"
    TECH_ARTIFACTS = "TECH_ARTIFACTS"
    CODEGEN = "CODEGEN"
    QA = "QA"
    FINALIZE = "FINALIZE"


@dataclass
class ProjectState:
    project_id: str
    req_session_id: str
    stage: Stage = Stage.REQ
    spec: Optional[dict[str, Any]] = None
    nontech_artifacts_md: Optional[dict[str, str]] = None
    technical_artifacts_md: Optional[dict[str, str]] = None
    angular_code_files: Optional[dict[str, str]] = None
    java_code_files: Optional[dict[str, str]] = None
    needs_redeploy: bool = False
    user_id: str = ""
    project_title: str | None = None
    project_description: str | None = None
    artifacts_summary: Optional[str] = None


_PROJECTS: dict[str, ProjectState] = {}


def get_or_create_project(
    project_id: str,
    req_session_id: str,
    user_id: str,
    project_title: str | None = None,
    project_description: str | None = None,
) -> ProjectState:
    """Get or create project, loading from persistent store if exists.
    
    Args:
        project_id: Project identifier
        req_session_id: Requirements gathering session ID
        user_id: Owner user ID
        project_title: Optional project name
        project_description: Optional project description
        
    Returns:
        ProjectState object at REQ stage
        
    Raises:
        ValueError: If user_id empty
    """
    if not user_id:
        raise ValueError("user_id is required and cannot be empty")

    from orchestration.persistent_store import load_project, save_project

    proj = _PROJECTS.get(project_id)

    if proj is None:
        proj = load_project(project_id)

    if proj is None:
        proj = ProjectState(
            project_id=project_id,
            req_session_id=req_session_id,
            user_id=user_id,
            project_title=project_title,
            project_description=project_description,
        )
        save_project(proj)
    else:
        if proj.user_id != user_id:
            raise PermissionError("Project is owned by a different user")

        proj.project_title = project_title or proj.project_title
        proj.project_description = project_description or proj.project_description
        save_project(proj)

    _PROJECTS[project_id] = proj
    return proj


def persist_project(project_id: str) -> None:
    """Save project to persistent store.
    
    Args:
        project_id: Project identifier
    """
    from orchestration.persistent_store import save_project

    proj = _PROJECTS.get(project_id)
    if proj is not None:
        save_project(proj)


def evict_project(project_id: str) -> None:
    """Remove project from memory cache, forcing next access to reload from DB."""
    _PROJECTS.pop(project_id, None)


def get_project(project_id: str) -> ProjectState | None:
    """Get project from memory cache or persistent store.
    
    Args:
        project_id: Project identifier
        
    Returns:
        ProjectState or None if not found
    """
    from orchestration.persistent_store import load_project

    proj = _PROJECTS.get(project_id)
    if proj is not None:
        return proj

    proj = load_project(project_id)
    if proj is not None:
        _PROJECTS[project_id] = proj

    return proj

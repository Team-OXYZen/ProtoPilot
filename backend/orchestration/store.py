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


@dataclass
class ProjectState:
    project_id: str
    req_session_id: str
    stage: Stage = Stage.REQ
    spec: Optional[dict[str, Any]] = None
    nontech_artifacts_md: Optional[dict[str, str]] = None
    technical_artifacts_md: Optional[dict[str, str]] = None
    generated_code_files: Optional[dict[str, str]] = None


_PROJECTS: dict[str, ProjectState] = {}


def get_or_create_project(project_id: str, req_session_id: str) -> ProjectState:
    from orchestration.persistent_store import load_project, save_project

    proj = _PROJECTS.get(project_id)

    if proj is None:
        proj = load_project(project_id)

    if proj is None:
        proj = ProjectState(project_id=project_id, req_session_id=req_session_id)
        save_project(proj)

    _PROJECTS[project_id] = proj
    return proj


def persist_project(project_id: str) -> None:
    from orchestration.persistent_store import save_project

    proj = _PROJECTS.get(project_id)
    if proj is not None:
        save_project(proj)


def get_project(project_id: str) -> ProjectState | None:
    from orchestration.persistent_store import load_project

    proj = _PROJECTS.get(project_id)
    if proj is not None:
        return proj

    proj = load_project(project_id)
    if proj is not None:
        _PROJECTS[project_id] = proj

    return proj
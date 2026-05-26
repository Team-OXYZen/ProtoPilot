from fastapi import HTTPException, status

from orchestration.store import ProjectState, get_project


def authenticated_user_id(
    current_user: dict[str, str],
    requested_user_id: str | None = None,
) -> str:
    user_id = current_user["username"]

    if requested_user_id is not None and requested_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested user does not match authenticated user",
        )

    return user_id


def get_owned_project(project_id: str, user_id: str) -> ProjectState:
    project = get_project(project_id)

    if project is None or project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project


def ensure_owned_project_or_missing(project_id: str, user_id: str) -> ProjectState | None:
    project = get_project(project_id)

    if project is not None and project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project

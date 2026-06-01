from fastapi import HTTPException, status

from orchestration.store import ProjectState, get_project


def authenticated_user_id(
    current_user: dict[str, str],
    requested_user_id: str | None = None,
) -> str:
    """Validate user authentication and return authenticated user ID.
    
    Args:
        current_user: Current authenticated user dict from JWT
        requested_user_id: Optional requested user (must match current if provided)
        
    Returns:
        Authenticated user ID (username)
        
    Raises:
        HTTPException: If requested user doesn't match authenticated user
    """
    user_id = current_user["username"]

    if requested_user_id is not None and requested_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested user does not match authenticated user",
        )

    return user_id


def get_owned_project(project_id: str, user_id: str) -> ProjectState:
    """Retrieve project only if owned by user.
    
    Args:
        project_id: Project identifier
        user_id: User identifier
        
    Returns:
        ProjectState object
        
    Raises:
        HTTPException: If project not found or not owned by user
    """
    project = get_project(project_id)

    if project is None or project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project


def ensure_owned_project_or_missing(project_id: str, user_id: str) -> ProjectState | None:
    """Check project ownership, allowing missing projects (for creation).
    
    Args:
        project_id: Project identifier
        user_id: User identifier
        
    Returns:
        ProjectState if exists and owned, None if missing, raises if owned by other user
        
    Raises:
        HTTPException: If project owned by different user
    """
    project = get_project(project_id)

    if project is not None and project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project

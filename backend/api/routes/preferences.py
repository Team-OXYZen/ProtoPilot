from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.logging_utils import log_event
from core.user_store import get_user_preferences, save_user_preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


class UserPreferencesRequest(BaseModel):
    preferences: dict[str, str] = Field(default_factory=dict)


@router.get("")
def read_preferences(current_user: dict[str, str] = Depends(get_current_user)):
    """Return non-secret preferences for the authenticated user."""
    username = current_user["username"]
    preferences = get_user_preferences(username)
    log_event("TOOL", "user_preferences_read", {"username": username, "keys": list(preferences.keys())}, status="ok")
    return {"preferences": preferences}


@router.put("")
def update_preferences(req: UserPreferencesRequest, current_user: dict[str, str] = Depends(get_current_user)):
    """Replace non-secret preferences for the authenticated user."""
    username = current_user["username"]
    try:
        preferences = save_user_preferences(username, req.preferences)
    except ValueError as exc:
        log_event("ERROR", "user_preferences_invalid", {"username": username, "error": str(exc)}, status="fail")
        raise HTTPException(status_code=400, detail=str(exc))

    log_event("TOOL", "user_preferences_saved", {"username": username, "keys": list(preferences.keys())}, status="ok")
    return {"preferences": preferences}

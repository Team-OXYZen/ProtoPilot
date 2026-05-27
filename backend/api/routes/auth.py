from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.user_store import create_user, ensure_user, get_password_hash

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, str]


def _ensure_demo_user() -> None:
    ensure_user("demo", hash_password("demo123"))


def _auth_response(username: str) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(username),
        user={"username": username},
    )


@router.post("/login", response_model=AuthResponse)
def login(req: AuthRequest):
    """Authenticate user with username and password.
    
    Args:
        req: Username and password credentials
        
    Returns:
        AuthResponse with JWT access token and user info
    """
    _ensure_demo_user()
    password_hash = get_password_hash(req.username)
    if password_hash is None or not verify_password(req.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return _auth_response(req.username)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(req: AuthRequest):
    """Create new user account.
    
    Args:
        req: Username and password for new account
        
    Returns:
        AuthResponse with JWT access token and user info
    """
    _ensure_demo_user()

    if not create_user(req.username, hash_password(req.password)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    return _auth_response(req.username)


@router.get("/me")
def me(current_user: dict[str, str] = Depends(get_current_user)):
    """Get current authenticated user info.
    
    Args:
        current_user: Current authenticated user from JWT
        
    Returns:
        dict with user object containing username
    """
    return {"user": current_user}

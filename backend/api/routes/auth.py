from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, str]


_users: dict[str, str] = {
    "demo": hash_password("demo123"),
}


def _auth_response(username: str) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(username),
        user={"username": username},
    )


@router.post("/login", response_model=AuthResponse)
def login(req: AuthRequest):
    password_hash = _users.get(req.username)
    if password_hash is None or not verify_password(req.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return _auth_response(req.username)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(req: AuthRequest):
    if req.username in _users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    _users[req.username] = hash_password(req.password)
    return _auth_response(req.username)


@router.get("/me")
def me(current_user: dict[str, str] = Depends(get_current_user)):
    return {"user": current_user}

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.core.auth import AUTH_PASSWORD, AUTH_USERNAME, SESSION_TOKEN
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "lc_session"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, response: Response):
    if req.username != AUTH_USERNAME or req.password != AUTH_PASSWORD:
        raise HTTPException(401, "Invalid username or password")
    # Set as a cookie (not just returned in the body) so the browser attaches
    # it automatically to <img>/<video>/<a download> requests too -- those
    # can't carry a custom Authorization header the way fetch() calls can.
    response.set_cookie(
        key=COOKIE_NAME, value=SESSION_TOKEN, httponly=True, samesite="lax",
        secure=settings.cookie_secure, path="/", max_age=60 * 60 * 24 * 30,
    )
    return LoginResponse(token=SESSION_TOKEN)

from fastapi import APIRouter, Depends, Request, Response

from app.container import Container
from app.deps import COOKIE_NAME, get_auth_service, get_container, get_current_user
from app.db.models import User
from app.schemas import Credentials, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str, container: Container) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=container.tokens.ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=container.settings.cookie_secure,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    body: Credentials,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    container: Container = Depends(get_container),
):
    user, token = await auth.register(body.email, body.password)
    _set_cookie(response, token, container)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    body: Credentials,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    container: Container = Depends(get_container),
):
    key = f"{body.email.lower()}|{request.client.host if request.client else ''}"
    await container.login_limiter.check(key)
    user, token = await auth.authenticate(body.email, body.password)
    await container.login_limiter.reset(key)
    _set_cookie(response, token, container)
    return user


@router.post("/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user

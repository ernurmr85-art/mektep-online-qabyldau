
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import COOKIE, DUMMY_HASH, MAX_AGE, DB, hash_password, issue_token, matches_password
from app.demo import ACCOUNTS
from app.models import User
from app.schemas import Register, Token, UserRead

router = APIRouter(prefix="/api/auth", tags=["Тіркелу және кіру"])
demo_router = APIRouter(prefix="/api/auth", tags=["Демо тіркелгілер"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(data: Register, db: DB):
    if len(data.password.encode()) > 72:
        raise HTTPException(422, "Құпиясөздің көлемі 72 байттан аспауы керек.")
    user = User(email=data.email.lower(), full_name=data.full_name, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Бұл электрондық пошта тіркелген.") from None
    return user


@router.post("/token", response_model=Token)
def login(request: Request, response: Response, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    valid = matches_password(form.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, "Электрондық пошта немесе құпиясөз қате.", headers={"WWW-Authenticate": "Bearer"})
    return login_response(request, response, user)


@demo_router.post("/demo/{role}", response_model=Token)
def demo_login(role: Literal["parent", "admin"], request: Request, response: Response, db: DB):
    if request.headers.get("X-Mektep-Portal") != "1":
        raise HTTPException(403, "Сұранысқа рұқсат берілмеді.")
    email, _name = ACCOUNTS[role]
    user = db.scalar(select(User).where(User.email == email, User.role == role))
    if user is None:
        raise HTTPException(503, "Демо тіркелгісі қолжетімсіз.")
    return login_response(request, response, user)


def login_response(request, response, user):
    token = issue_token(user)
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("X-Mektep-Portal") == "1":
        response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax",
                            secure=request.url.scheme == "https")
    return Token(access_token=token)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    if request.headers.get("X-Mektep-Portal") != "1":
        raise HTTPException(403, "Сұранысқа рұқсат берілмеді.")
    response.delete_cookie(COOKIE, secure=request.url.scheme == "https", httponly=True, samesite="lax")

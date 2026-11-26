
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.models import User
from database import DEMO_MODE, get_db

COOKIE = "mektep_demo_session" if DEMO_MODE else "mektep_session"
MAX_AGE = 8 * 60 * 60
SECRET = (None if DEMO_MODE else os.environ.get("MEKTEP_JWT_SECRET")) or secrets.token_urlsafe(48)
ALGORITHM = "HS256"
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


DUMMY_HASH = hash_password("unregistered-account")


def matches_password(password, password_hash):
    encoded = password.encode()
    return len(encoded) <= 72 and bcrypt.checkpw(encoded, password_hash.encode())


def issue_token(user):
    expiry = datetime.now(timezone.utc) + timedelta(seconds=MAX_AGE)
    return jwt.encode({"sub": str(user.id), "exp": expiry}, SECRET, algorithm=ALGORITHM)


def user_from_token(db, token):
    if not token:
        return None
    try:
        claims = jwt.decode(token, SECRET, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})
        return db.get(User, int(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        return None


def page_user(request: Request, db: DB):
    return user_from_token(db, request.cookies.get(COOKIE))


def current_user(request: Request, db: DB, bearer: Annotated[str | None, Depends(oauth2)]):
    token = bearer or request.cookies.get(COOKIE)
    user = user_from_token(db, token)
    if not user:
        raise HTTPException(401, "Жүйеге кіріңіз.", headers={"WWW-Authenticate": "Bearer"})
    if not bearer and request.method != "GET" and request.headers.get("X-Mektep-Portal") != "1":
        raise HTTPException(403, "Сұранысқа рұқсат берілмеді.")
    return user


def parent_only(user: Annotated[User, Depends(current_user)]):
    if user.role != "parent":
        raise HTTPException(403, "Бұл әрекет ата-анаға қолжетімді.")
    return user


def admin_only(user: Annotated[User, Depends(current_user)]):
    if user.role != "admin":
        raise HTTPException(403, "Бұл әрекет қабылдау комиссиясына қолжетімді.")
    return user


Parent = Annotated[User, Depends(parent_only)]
Admin = Annotated[User, Depends(admin_only)]

"""User registration, login, and JWT authentication."""

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db, read_secret

router = APIRouter(prefix="/auth", tags=["authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
password_hash = PasswordHash.recommended()
jwt_secret_key = read_secret("jwt_secret_key")
access_token_expire_minutes = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)
if access_token_expire_minutes <= 0:
    raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive.")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=access_token_expire_minutes)
    return jwt.encode(
        {"sub": username, "iat": now, "exp": expires_at},
        jwt_secret_key,
        algorithm="HS256",
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    try:
        payload = jwt.decode(
            token,
            jwt_secret_key,
            algorithms=["HS256"],
        )
    except jwt.InvalidTokenError as exc:
        raise _unauthorized() from exc

    username = payload.get("sub")
    if not isinstance(username, str) or not username:
        raise _unauthorized()

    user = db.scalar(
        select(models.User).where(models.User.username == username)
    )
    if user is None or not user.is_active:
        raise _unauthorized()

    return user


@router.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    data: schemas.UserCreate,
    db: Session = Depends(get_db),
) -> models.User:
    existing_user = db.scalar(
        select(models.User).where(models.User.username == data.username)
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        )

    user = models.User(
        username=data.username,
        hashed_password=password_hash.hash(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        ) from exc

    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> schemas.Token:
    user = db.scalar(
        select(models.User).where(
            models.User.username == form_data.username.strip()
        )
    )
    if (
        user is None
        or not user.is_active
        or not password_hash.verify(form_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return schemas.Token(
        access_token=create_access_token(user.username),
        token_type="bearer",
    )


@router.get("/me", response_model=schemas.UserRead)
def read_current_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    return current_user

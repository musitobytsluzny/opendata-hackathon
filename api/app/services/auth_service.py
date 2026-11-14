from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.database.connection import settings
from app.models.user import User
from app.services.passwords import verify_password


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()

    if user is None:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def create_access_token(user_id: int, username: str):
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    return token

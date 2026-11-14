from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth_service import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=UserRead)
def current_user(user: User = Depends(get_current_user)):
    return user


@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, login_data.username, login_data.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávné uživatelské jméno nebo heslo.",
        )

    token = create_access_token(user.id, user.username)

    return {"access_token": token, "token_type": "bearer"}

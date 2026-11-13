from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import require_admin, require_self_or_admin
from app.schemas.user import RoleUpdate, UserCreate, UserRead, UserUpdate
from app.services.user_service import (
    create_user,
    delete_user,
    get_user_by_id,
    get_users,
    update_user,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    try:
        return create_user(db, user_data)

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")


@router.get("/", response_model=list[UserRead], dependencies=[Depends(require_admin)])
def read_users(db: Session = Depends(get_db)):
    return get_users(db)


@router.get("/{user_id}", response_model=UserRead, dependencies=[Depends(require_self_or_admin)])
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return user


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(require_self_or_admin)])
def update_user_endpoint(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db)):
    user = update_user(db, user_id, user_data)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_self_or_admin)],
)
def delete_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    deleted = delete_user(db, user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


@router.patch("/{user_id}/role", response_model=UserRead, dependencies=[Depends(require_admin)])
def change_role(user_id: int, data: RoleUpdate, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = data.role.value
    db.commit()
    db.refresh(user)
    return user

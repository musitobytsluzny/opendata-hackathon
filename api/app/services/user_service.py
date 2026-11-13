from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.models.profile import Profile
from app.models.user import User
from app.schemas.user import UserCreate

password_hash = PasswordHash.recommended()


def create_user(db: Session, user_data: UserCreate):
    # Zahashujeme heslo, nikdy neukládáme původní heslo
    hashed_password = password_hash.hash(user_data.password)

    # Vytvoříme uživatele a jeho profil
    user = User(
        username=user_data.username,
        password_hash=hashed_password,
        profile=Profile(firstname=user_data.profile.firstname, lastname=user_data.profile.lastname),
    )

    # Uložíme obě propojené tabulky
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def get_users(db: Session):
    return db.query(User).all()


def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def update_user(db: Session, user_id: int, user_data):
    user = get_user_by_id(db, user_id)

    if user is None:
        return None

    update_data = user_data.model_dump(exclude_unset=True)

    if "password" in update_data:
        update_data["password_hash"] = password_hash.hash(update_data.pop("password"))

    profile_data = update_data.pop("profile", None)

    for key, value in update_data.items():
        setattr(user, key, value)

    if profile_data is not None:
        for key, value in profile_data.items():
            setattr(user.profile, key, value)

    db.commit()
    db.refresh(user)

    return user


def delete_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)

    if user is None:
        return False

    db.delete(user)
    db.commit()

    return True

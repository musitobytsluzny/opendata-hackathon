
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.models.user import User
from app.models.profile import Profile
from app.schemas.user import UserCreate


password_hash = PasswordHash.recommended()


def create_user(db: Session, user_data: UserCreate):
    # Zahashujeme heslo, nikdy neukládáme původní heslo
    hashed_password = password_hash.hash(user_data.password)

    # Vytvoříme uživatele a jeho profil
    user = User(
        username=user_data.username,
        password_hash=hashed_password,
        profile=Profile(
            firstname=user_data.profile.firstname,
            lastname=user_data.profile.lastname
        )
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

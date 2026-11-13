"""Promote an existing account using trusted shell access, never public registration."""

import argparse

from app.database.connection import SessionLocal
from app.models import User
from app.roles import Role
from sqlalchemy import select


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.username == args.username).with_for_update())
        if user is None:
            parser.error("Register the account before promoting it")
        user.role = Role.ADMIN.value
    print("Admin role granted")


if __name__ == "__main__":
    main()

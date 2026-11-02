
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def main():
    username = input("Enter username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return

    role = input("Enter role (ADMIN/ACCOUNTS/VIEWER): ").strip().upper()
    if role not in ("ADMIN", "ACCOUNTS", "VIEWER"):
        print("Invalid role.")
        return

    password = getpass("Enter password: ")
    if len(password) < 12:
        print("Use a password with at least 12 characters.")
        return

    confirm_password = getpass("Confirm password: ")
    if password != confirm_password:
        print("Passwords do not match.")
        return

    with SessionLocal() as db:
        existing_user = db.scalar(
            select(User).where(User.username == username)
        )

        if existing_user:
            print("That username already exists.")
            return

        user = User(
            username=username,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()

        print(f"{role} user '{username}' created successfully.")


if __name__ == "__main__":
    main()

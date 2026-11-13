from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def main():
    print("=== IT Head Account Setup ===")

    username = input("Enter IT Head username: ").strip()
    email = input("Enter IT Head email: ").strip() or None

    if not username:
        print("Username cannot be empty.")
        return

    password = getpass("Enter IT Head password: ")
    confirm_password = getpass("Confirm IT Head password: ")

    if not password:
        print("Password cannot be empty.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(User.username == username)
        )

        if existing:
            print(
                "A user with this username already exists. "
                "No changes were made."
            )
            return

        if email:
            existing_email = db.scalar(
                select(User).where(User.email == email)
            )

            if existing_email:
                print(
                    "This email is already registered. "
                    "No changes were made."
                )
                return

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role="IT_HEAD",
            is_active=True,
        )

        db.add(user)
        db.commit()

        print("\nIT Head account created successfully.")
        print(f"Username: {username}")
        print("Role: IT_HEAD")


if __name__ == "__main__":
    main()
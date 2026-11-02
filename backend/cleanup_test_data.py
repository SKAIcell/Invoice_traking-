from sqlalchemy import text

from app.db.session import engine


def main():
    with engine.begin() as connection:
        print("Database:", connection.execute(
            text("SELECT DATABASE()")
        ).scalar())

        print("Before cleanup:")
        for table in ("payments", "invoices", "orders", "users"):
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
            print(f"  {table}: {count}")

        confirmation = input(
            "\nDelete ALL payment, invoice, and order records? Type YES to continue: "
        )

        if confirmation != "YES":
            print("Cleanup cancelled. No records were deleted.")
            return

        connection.execute(text("DELETE FROM payments"))
        connection.execute(text("DELETE FROM invoices"))
        connection.execute(text("DELETE FROM orders"))

        print("\nCleanup completed.")
        print("After cleanup:")
        for table in ("payments", "invoices", "orders", "users"):
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
            print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
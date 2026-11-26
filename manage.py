
from argparse import ArgumentParser
from datetime import date, timedelta
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import select

from app.auth import hash_password
from app.models import Direction, User
from app.schemas import Register
from app.setup import initialize_database
from database import SessionLocal


def seed_catalog(db):
    today = date.today()
    examples = [
        (1, "kk", "Бастауыш сыныпқа қабылдау"),
        (1, "ru", "Бірінші сыныпқа қабылдау"),
        (2, "kk", "Екінші сыныпқа ауысу"),
        (3, "kk", "Үшінші сыныпқа ауысу"),
        (5, "kk", "Бесінші сыныпқа қабылдау"),
        (5, "ru", "Бесінші сыныпқа ауысу"),
        (10, "kk", "Оныншы сыныпқа қабылдау"),
        (10, "ru", "Жоғары сыныпқа қабылдау"),
    ]
    added = 0
    for grade, language, title in examples:
        if db.scalar(select(Direction.id).where(Direction.title == title, Direction.language == language)):
            continue
        db.add(Direction(
            title=title, grade=grade, language=language,
            description=f"{grade}-сыныпқа қабылдауға арналған оқу жобасының үлгі бағыты.",
            documents="Оқушының туу туралы куәлігі\nАта-ананың немесе заңды өкілдің жеке куәлігі",
            opens_on=today, closes_on=today + timedelta(days=180), active=True, capacity=25,
        ))
        added += 1
    db.commit()
    print(f"Catalog directions added: {added}")


def create_admin(db, email):
    if db.scalar(select(User.id).where(User.email == email.strip().lower())):
        raise SystemExit("This email is already registered.")
    password = getpass("Admin password (8 or more characters): ")
    if password != getpass("Repeat password: ") or len(password.encode()) > 72:
        raise SystemExit("Passwords must match and may contain up to 72 bytes.")
    try:
        data = Register(email=email, full_name="Қабылдау комиссиясы", password=password)
    except ValidationError:
        raise SystemExit("Enter a valid email and a password of at least 8 characters.") from None
    db.add(User(email=data.email.lower(), full_name=data.full_name, password_hash=hash_password(password), role="admin"))
    db.commit()
    print(f"Commission account created: {data.email}")


def main():
    parser = ArgumentParser(description="Mektep database tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed")
    admin = commands.add_parser("create-admin")
    admin.add_argument("email")
    args = parser.parse_args()
    initialize_database()
    with SessionLocal() as db:
        if args.command == "seed":
            seed_catalog(db)
        else:
            create_admin(db, args.email)


if __name__ == "__main__":
    main()

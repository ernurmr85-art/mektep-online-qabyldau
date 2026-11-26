
from sqlalchemy import select

from app.auth import hash_password
from app.models import User
from database import SessionLocal, lock_writes

PASSWORD = "Mektep-Demo31"
ACCOUNTS = {
    "parent": ("parent@mektep.example", "Демо ата-ана"),
    "admin": ("commission@mektep.example", "Демо комиссия"),
}


def setup_demo():
    from manage import seed_catalog

    with SessionLocal() as db:
        lock_writes(db)
        existing = set(db.scalars(select(User.email).where(
            User.email.in_([email for email, _name in ACCOUNTS.values()])
        )))
        if len(existing) == len(ACCOUNTS):
            return
        for role, (email, name) in ACCOUNTS.items():
            if email not in existing:
                db.add(User(email=email, full_name=name, password_hash=hash_password(PASSWORD), role=role))
        seed_catalog(db)  # Commits the demo catalog and the accounts together.

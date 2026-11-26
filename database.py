
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parent
DEMO_MODE = os.environ.get("MEKTEP_DEMO") == "1"
DATA_DIR = Path(os.environ.get("MEKTEP_DATA_DIR", ROOT / "data")).resolve()
if DEMO_MODE:
    DATA_DIR = DATA_DIR / "demo"
DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{(DATA_DIR / 'mektep.sqlite3').as_posix()}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _record):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.create_function("casefold", 1, str.casefold, deterministic=True)


class Base(DeclarativeBase):
    pass


def lock_writes(session):
    # Hold SQLite's writer reservation while checking capacity or changing related records.
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def get_db():
    with SessionLocal() as session:
        yield session

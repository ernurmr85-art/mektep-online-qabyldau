
from sqlalchemy import inspect

from app import models  # Register models before creating the tables.
from database import Base, engine


def initialize_database():
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        Base.metadata.create_all(connection)
        columns = inspect(connection).get_columns("directions")
        if "capacity" not in {column["name"] for column in columns}:
            connection.exec_driver_sql("ALTER TABLE directions ADD COLUMN capacity INTEGER")

        # Recover the milestones recorded by older versions.
        for kind, actor, note, timestamp, condition in (
            ("'created'", "parent_id", "NULL", "created_at", "1 = 1"),
            ("'submitted'", "parent_id", "NULL", "submitted_at", "submitted_at IS NOT NULL"),
            ("a.status", "reviewer_id", "decision_note", "decided_at",
             "a.status IN ('accepted', 'rejected') AND decided_at IS NOT NULL"),
        ):
            connection.exec_driver_sql(f"""
                INSERT INTO application_events (application_id, actor_id, kind, note, occurred_at)
                SELECT id, {actor}, {kind}, {note}, {timestamp} FROM applications AS a
                WHERE {condition} AND NOT EXISTS (
                    SELECT 1 FROM application_events AS event
                    WHERE event.application_id = a.id AND event.kind = {kind}
                )
            """)

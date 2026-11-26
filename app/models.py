
from datetime import date, datetime, timedelta, timezone

PORTAL_TZ = timezone(timedelta(hours=5))

from sqlalchemy import Date, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from database import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(15), default="parent")


class Direction(Base):
    __tablename__ = "directions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    grade: Mapped[int] = mapped_column(index=True)
    language: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(Text)
    documents: Mapped[str] = mapped_column(Text)
    opens_on: Mapped[date] = mapped_column(Date)
    closes_on: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(default=True)
    capacity: Mapped[int | None] = mapped_column()

    @property
    def document_slots(self):
        return list(dict.fromkeys(line.strip() for line in self.documents.splitlines() if line.strip()))

    @property
    def seats_remaining(self):
        if self.capacity is None:
            return None
        return max(0, self.capacity - self.accepted_count)

    @property
    def accepting(self):
        return self.active and self.opens_on <= date.today() <= self.closes_on


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("direction_id", "iin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    direction_id: Mapped[int] = mapped_column(ForeignKey("directions.id"), index=True)
    student_name: Mapped[str] = mapped_column(String(100))
    iin: Mapped[str] = mapped_column(String(12))
    parent_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(15), default="draft", index=True)
    decision_note: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    direction: Mapped[Direction] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship(order_by="Attachment.id")
    events: Mapped[list["ApplicationEvent"]] = relationship(order_by="ApplicationEvent.id")


class Attachment(Base):
    __tablename__ = "application_attachments"
    __table_args__ = (UniqueConstraint("application_id", "document"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    document: Mapped[str] = mapped_column(String(160))
    filename: Mapped[str] = mapped_column(String(180))
    media_type: Mapped[str] = mapped_column(String(32))
    size: Mapped[int] = mapped_column()
    contents: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now)


Direction.accepted_count = column_property(
    select(func.count()).select_from(Application)
    .where(Application.direction_id == Direction.id, Application.status == "accepted")
    .correlate_except(Application).scalar_subquery()
)

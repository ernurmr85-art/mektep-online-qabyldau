
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.auth import Admin, DB, Parent
from app.models import PORTAL_TZ, Application, ApplicationEvent, now
from app.routers.catalog import get_direction
from app.schemas import ApplicationCreate, ApplicationDetail, ApplicationFields, ApplicationRead, Decision, ReviewStatus
from database import lock_writes

router = APIRouter(prefix="/api/applications", tags=["Өтінімдер"])
EDITABLE = ("draft", "revision")


def parent_application(db, parent_id, app_id):
    item = db.scalar(select(Application).where(Application.id == app_id, Application.parent_id == parent_id))
    if not item:
        raise HTTPException(404, "Өтінім табылмады.")
    return item


def submitted_application(db, app_id):
    item = db.get(Application, app_id)
    if not item or item.status == "draft":
        raise HTTPException(404, "Жіберілген өтінім табылмады.")
    return item


def parent_applications(db, parent_id):
    return db.scalars(
        select(Application).options(joinedload(Application.direction))
        .where(Application.parent_id == parent_id).order_by(Application.id.desc())
    ).all()


def day_start_utc(day):
    return datetime.combine(day, time.min, PORTAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def commission_queue(db, status=None, q="", direction_id=None, date_from=None, date_to=None, *, include_details=False):
    query = (select(Application).options(joinedload(Application.direction))
             .where(Application.status != "draft"))
    if status == "waitlisted":
        query = query.order_by(Application.direction_id, Application.decided_at, Application.id)
    else:
        query = query.order_by(Application.submitted_at.desc(), Application.id.desc())
    if include_details:
        query = query.options(selectinload(Application.attachments), selectinload(Application.events))
    if status:
        query = query.where(Application.status == status)
    if text := q.strip().casefold():
        number = text.removeprefix("№").removeprefix("#").strip()
        if number.isascii() and number.isdecimal() and len(number) <= 18:
            query = query.where(Application.id == int(number))
        else:
            query = query.where(or_(
                func.casefold(Application.student_name).contains(text, autoescape=True),
                func.casefold(Application.parent_name).contains(text, autoescape=True),
            ))
    if direction_id is not None:
        query = query.where(Application.direction_id == direction_id)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Басталу күні аяқталу күнінен кейін болмауы керек.")
    if date_from and date_from > date.min:
        query = query.where(Application.submitted_at >= day_start_utc(date_from))
    if date_to and date_to < date.max:
        query = query.where(Application.submitted_at < day_start_utc(date_to + timedelta(days=1)))
    return db.scalars(query).all()


def commit_application(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Осы бағытқа бұл ЖСН бойынша өтінім бар немесе бағыт қолжетімсіз.") from None


def require_editable(item):
    if item.status not in EDITABLE:
        raise HTTPException(409, "Өтінімді тек жоба немесе толықтыру күйінде өңдеуге болады.")


def log_event(db, item, actor_id, kind, *, note=None, occurred_at=None):
    db.add(ApplicationEvent(application_id=item.id, actor_id=actor_id, kind=kind, note=note,
                            occurred_at=occurred_at or now()))


@router.get("", response_model=list[ApplicationRead])
def mine(db: DB, parent: Parent):
    return parent_applications(db, parent.id)


@router.get("/review", response_model=list[ApplicationRead])
def review_queue(db: DB, _admin: Admin, status: ReviewStatus | None = None,
                 q: Annotated[str, Query(max_length=100)] = "",
                 direction_id: Annotated[int | None, Query(gt=0)] = None,
                 date_from: date | None = None, date_to: date | None = None):
    return commission_queue(db, status, q, direction_id, date_from, date_to)


@router.get("/review/{app_id}", response_model=ApplicationDetail)
def review_detail(app_id: int, db: DB, _admin: Admin):
    return submitted_application(db, app_id)


@router.get("/{app_id}", response_model=ApplicationDetail)
def detail(app_id: int, db: DB, parent: Parent):
    return parent_application(db, parent.id, app_id)


@router.post("", response_model=ApplicationRead, status_code=201)
def create(data: ApplicationCreate, db: DB, parent: Parent):
    direction = get_direction(db, data.direction_id)
    if not direction.accepting:
        raise HTTPException(409, "Бұл бағыт бойынша қабылдау қазір жабық.")
    item = Application(parent_id=parent.id, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Осы бағытқа бұл ЖСН бойынша өтінім бар немесе бағыт қолжетімсіз.") from None
    log_event(db, item, parent.id, "created", occurred_at=item.created_at)
    commit_application(db)
    return item


@router.put("/{app_id}", response_model=ApplicationRead)
def edit(app_id: int, data: ApplicationFields, db: DB, parent: Parent):
    item = parent_application(db, parent.id, app_id)
    require_editable(item)
    result = db.execute(update(Application).where(Application.id == app_id, Application.status.in_(EDITABLE))
                        .values(**data.model_dump()))
    if not result.rowcount:
        raise HTTPException(409, "Өтінім мәртебесі өзгерді. Бетті жаңартыңыз.")
    commit_application(db)
    return item


@router.delete("/{app_id}", status_code=204)
def remove(app_id: int, db: DB, parent: Parent):
    item = parent_application(db, parent.id, app_id)
    if item.status != "draft":
        raise HTTPException(409, "Тек жіберілмеген жобаны жоюға болады.")
    result = db.execute(delete(Application).where(Application.id == app_id, Application.status == "draft"))
    if not result.rowcount:
        raise HTTPException(409, "Өтінім мәртебесі өзгерді. Бетті жаңартыңыз.")
    db.commit()


@router.post("/{app_id}/submit", response_model=ApplicationRead)
def submit(app_id: int, db: DB, parent: Parent):
    lock_writes(db)
    item = parent_application(db, parent.id, app_id)
    require_editable(item)
    is_revision = item.status == "revision"
    if not is_revision and not item.direction.accepting:
        raise HTTPException(409, "Қабылдау мерзімі аяқталды немесе бағыт жабық.")
    timestamp = now()
    item.status = "pending"
    item.submitted_at = timestamp
    item.decision_note = None
    item.decided_at = None
    item.reviewer_id = None
    log_event(db, item, parent.id, "resubmitted" if is_revision else "submitted", occurred_at=timestamp)
    db.commit()
    return item


def waiting_position(db, item):
    if item.status != "waitlisted":
        return None
    earlier = or_(
        Application.decided_at < item.decided_at,
        (Application.decided_at == item.decided_at) & (Application.id < item.id),
    )
    return 1 + db.scalar(select(func.count()).select_from(Application).where(
        Application.direction_id == item.direction_id, Application.status == "waitlisted", earlier,
    ))


def decide_acceptance(db, item):
    direction = item.direction
    queue_head = db.scalar(select(Application.id).where(
        Application.direction_id == direction.id, Application.status == "waitlisted"
    ).order_by(Application.decided_at, Application.id).limit(1))
    seat_available = direction.seats_remaining is None or direction.seats_remaining > 0
    if item.status == "waitlisted":
        if not seat_available:
            raise HTTPException(409, "Бұл бағытта бос орын жоқ.")
        if queue_head != item.id:
            raise HTTPException(409, f"Алдымен кезектегі №{queue_head} өтінімді қараңыз.")
        return "accepted"
    return "accepted" if seat_available and queue_head is None else "waitlisted"


@router.put("/{app_id}/decision", response_model=ApplicationRead)
def decide(app_id: int, data: Decision, db: DB, admin: Admin):
    lock_writes(db)
    item = submitted_application(db, app_id)
    if item.status not in ("pending", "waitlisted") or (item.status == "waitlisted" and data.status == "revision"):
        raise HTTPException(409, "Өтінім қазіргі күйінде бұл шешімді қабылдамайды.")
    decision = decide_acceptance(db, item) if data.status == "accepted" else data.status
    timestamp = now()
    item.status = decision
    item.decision_note = data.note or None
    item.decided_at = timestamp
    item.reviewer_id = admin.id
    log_event(db, item, admin.id, decision, note=item.decision_note, occurred_at=timestamp)
    db.commit()
    if decision == "accepted":
        db.expire(item.direction, ["accepted_count"])
    return item

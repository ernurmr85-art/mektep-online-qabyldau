
from math import ceil
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import Admin, DB
from app.models import Direction
from app.schemas import DirectionCreate, DirectionPage, DirectionRead, Grade, Language
from database import lock_writes

router = APIRouter(prefix="/api/directions", tags=["Қабылдау бағыттары"])
PER_PAGE = 6
LANGUAGES = {"kk": "Қазақ тілі", "ru": "Орыс тілі"}


def list_directions(db, q="", grade=None, language=None, page=1):
    criteria = [Direction.active.is_(True)]
    if q.strip():
        criteria.append(func.casefold(Direction.title).contains(q.strip().casefold(), autoescape=True))
    if grade is not None:
        criteria.append(Direction.grade == grade)
    if language:
        criteria.append(Direction.language == language)
    total = db.scalar(select(func.count()).select_from(Direction).where(*criteria))
    pages = max(1, ceil(total / PER_PAGE))
    page = min(page, pages)
    rows = db.scalars(
        select(Direction).where(*criteria).order_by(Direction.grade, Direction.id)
        .offset((page - 1) * PER_PAGE).limit(PER_PAGE)
    ).all()
    return DirectionPage(items=rows, total=total, page=page, pages=pages)


def get_direction(db, direction_id, *, public=True):
    direction = db.get(Direction, direction_id)
    if not direction or (public and not direction.active):
        raise HTTPException(404, "Қабылдау бағыты табылмады.")
    return direction


@router.get("", response_model=DirectionPage)
def browse(db: DB, q: Annotated[str, Query(max_length=100)] = "", grade: Grade | None = None,
           language: Language | None = None, page: Annotated[int, Query(ge=1)] = 1):
    return list_directions(db, q, grade, language, page)


@router.get("/manage", response_model=list[DirectionRead])
def manage(db: DB, _admin: Admin):
    return db.scalars(select(Direction).order_by(Direction.grade, Direction.id)).all()


@router.get("/{direction_id}", response_model=DirectionRead)
def detail(direction_id: int, db: DB):
    return get_direction(db, direction_id)


@router.post("", response_model=DirectionRead, status_code=201)
def create(data: DirectionCreate, db: DB, _admin: Admin):
    direction = Direction(**data.model_dump())
    db.add(direction)
    db.commit()
    return direction


@router.put("/{direction_id}", response_model=DirectionRead)
def edit(direction_id: int, data: DirectionCreate, db: DB, _admin: Admin):
    lock_writes(db)
    direction = get_direction(db, direction_id, public=False)
    if data.capacity is not None and data.capacity < direction.accepted_count:
        raise HTTPException(409, "Орын саны қабылданған оқушылар санынан аз болмауы керек.")
    changes = data.model_dump()
    if "capacity" not in data.model_fields_set:
        changes.pop("capacity")
    for field, value in changes.items():
        setattr(direction, field, value)
    db.commit()
    return direction


@router.delete("/{direction_id}", status_code=204)
def delete(direction_id: int, db: DB, _admin: Admin):
    direction = get_direction(db, direction_id, public=False)
    db.delete(direction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Бұл бағытта өтінімдер бар. Оны каталогтан жасыруға болады.") from None


from datetime import date, timezone
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.auth import DB, page_user
from app.models import PORTAL_TZ, Direction, User
from app.routers.applications import commission_queue, parent_application, parent_applications, waiting_position
from app.routers.catalog import LANGUAGES, get_direction, list_directions
from app.schemas import Grade, Language, ReviewStatus
from database import DEMO_MODE, ROOT

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=ROOT / "templates")
templates.env.globals.update(
    demo_mode=DEMO_MODE,
    languages=LANGUAGES,
    statuses={
        "draft": "Жоба", "pending": "Қаралуда", "revision": "Толықтыру қажет",
        "waitlisted": "Күту тізімінде", "accepted": "Қабылданды", "rejected": "Бас тартылды",
    },
    event_labels={
        "created": "Өтінім жобасы жасалды", "submitted": "Комиссияға жіберілді",
        "resubmitted": "Қайта жіберілді", "revision": "Толықтыруға қайтарылды",
        "waitlisted": "Күту тізіміне қосылды", "accepted": "Қабылданды", "rejected": "Бас тартылды",
    },
)
Viewer = Annotated[User | None, Depends(page_user)]


def local_date(timestamp, format="%d.%m.%Y"):
    return timestamp.replace(tzinfo=timezone.utc).astimezone(PORTAL_TZ).strftime(format)


templates.env.filters["local_date"] = local_date


def render(request, template, user, **context):
    response = templates.TemplateResponse(request, template, {"user": user, **context})
    response.headers["Cache-Control"] = "no-store"
    return response


def redirect(path):
    return RedirectResponse(path, status_code=303)


def role_gate(user, role):
    if not user:
        return redirect("/login")
    if user.role != role:
        raise HTTPException(403, "Бұл бетке кіруге рұқсат жоқ.")
    return None


@router.get("/")
def home(request: Request, user: Viewer, db: DB):
    featured = list_directions(db).items[:3]
    return render(request, "index.html", user, featured=featured)


@router.get("/directions")
def catalog(request: Request, user: Viewer, db: DB, q: Annotated[str, Query(max_length=100)] = "",
            grade: Grade | Literal[""] | None = None, language: Language | Literal[""] | None = None,
            page: Annotated[int, Query(ge=1)] = 1):
    result = list_directions(db, q, grade or None, language or None, page)
    filters = {key: value for key, value in {"q": q, "grade": grade, "language": language}.items() if value}
    links = {number: "/directions?" + urlencode({**filters, "page": number})
             for number in (result.page - 1, result.page + 1) if 1 <= number <= result.pages}
    return render(request, "catalog.html", user, result=result, filters=filters, links=links)


@router.get("/directions/{direction_id}")
def direction_page(direction_id: int, request: Request, user: Viewer, db: DB):
    return render(request, "direction.html", user, direction=get_direction(db, direction_id))


@router.get("/login")
def login(request: Request, user: Viewer, direction: Annotated[int | None, Query(gt=0)] = None):
    if user:
        return redirect("/admin" if user.role == "admin" else "/cabinet")
    return render(request, "account.html", None, register=False, direction=direction, registered=request.query_params.get("registered") == "1")


@router.get("/register")
def register(request: Request, user: Viewer, direction: Annotated[int | None, Query(gt=0)] = None):
    if user:
        return redirect("/admin" if user.role == "admin" else "/cabinet")
    return render(request, "account.html", None, register=True, direction=direction)


@router.get("/account")
def account(user: Viewer, direction: Annotated[int | None, Query(gt=0)] = None):
    if not user:
        return redirect("/login")
    if user.role == "admin":
        return redirect("/admin")
    return redirect(f"/cabinet/new/{direction}" if direction else "/cabinet")


@router.get("/cabinet")
def cabinet(request: Request, user: Viewer, db: DB):
    if gate := role_gate(user, "parent"):
        return gate
    return render(request, "cabinet.html", user, applications=parent_applications(db, user.id))


@router.get("/cabinet/new/{direction_id}")
def new_application(direction_id: int, request: Request, user: Viewer, db: DB):
    if gate := role_gate(user, "parent"):
        return gate
    direction = get_direction(db, direction_id)
    if not direction.accepting:
        raise HTTPException(409, "Бұл бағыт бойынша қабылдау қазір жабық.")
    return render(request, "application.html", user, direction=direction, item=None)


@router.get("/cabinet/{app_id}")
def application(app_id: int, request: Request, user: Viewer, db: DB):
    if gate := role_gate(user, "parent"):
        return gate
    item = parent_application(db, user.id, app_id)
    return render(request, "application.html", user, direction=item.direction, item=item,
                  wait_position=waiting_position(db, item))


@router.get("/admin")
def admin(request: Request, user: Viewer, db: DB,
          status: ReviewStatus | Literal[""] | None = None, q: Annotated[str, Query(max_length=100)] = "",
          direction_id: Annotated[int, Query(gt=0)] | Literal[""] | None = None,
          date_from: date | Literal[""] | None = None, date_to: date | Literal[""] | None = None):
    if gate := role_gate(user, "admin"):
        return gate
    directions = db.scalars(select(Direction).order_by(Direction.grade, Direction.id)).all()
    applications = commission_queue(db, status or None, q, direction_id or None, date_from or None,
                                    date_to or None, include_details=True)
    filters = {"status": status, "q": q, "direction_id": direction_id, "date_from": date_from, "date_to": date_to}
    target = "/admin"
    if query := urlencode({key: value for key, value in filters.items() if value}):
        target += "?" + query
    return render(request, "admin.html", user, applications=applications, directions=directions,
                  filters=filters, target=target)


@router.get("/admin/directions")
def admin_directions(request: Request, user: Viewer, db: DB):
    if gate := role_gate(user, "admin"):
        return gate
    directions = db.scalars(select(Direction).order_by(Direction.grade, Direction.id)).all()
    return render(request, "manage.html", user, directions=directions)


@router.get("/admin/directions/new")
def admin_direction_new(request: Request, user: Viewer):
    if gate := role_gate(user, "admin"):
        return gate
    return render(request, "direction_form.html", user, item=None)


@router.get("/admin/directions/{direction_id}")
def admin_direction_edit(direction_id: int, request: Request, user: Viewer, db: DB):
    if gate := role_gate(user, "admin"):
        return gate
    return render(request, "direction_form.html", user, item=get_direction(db, direction_id, public=False))


from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.routing import APIRoute
from sqlalchemy import func, select

from app.auth import DB, Parent, current_user
from app.models import Attachment, User
from app.routers.applications import parent_application, require_editable, submitted_application
from app.schemas import AttachmentRead
from database import lock_writes

MAX_FILE_SIZE = 5 * 1024 * 1024
FILE_TYPES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)


class BoundedUploadRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate_size(request: Request):
            if request.method == "POST":
                length = request.headers.get("content-length", "")
                if not length.isascii() or not length.isdecimal():
                    raise HTTPException(411, "Жүктеу көлемі көрсетілуі керек.")
                if len(length) > 8 or int(length) > MAX_FILE_SIZE + 64 * 1024:
                    raise HTTPException(413, "Файл көлемі 5 МБ-тан аспауы керек.")
            return await handler(request)

        return validate_size


router = APIRouter(prefix="/api/applications/{app_id}/attachments", tags=["Өтінім құжаттары"],
                   route_class=BoundedUploadRoute)


def get_attachment(db, app_id, attachment_id):
    record = db.scalar(select(Attachment).where(
        Attachment.id == attachment_id, Attachment.application_id == app_id,
    ))
    if record is None:
        raise HTTPException(404, "Құжат табылмады.")
    return record


@router.post("", response_model=AttachmentRead, status_code=201)
def upload(app_id: int, db: DB, parent: Parent, document: Annotated[str, Form(min_length=1, max_length=160)],
           file: Annotated[UploadFile, File()]):
    parent_application(db, parent.id, app_id)
    contents = file.file.read(MAX_FILE_SIZE + 1)
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(413, "Файл көлемі 5 МБ-тан аспауы керек.")
    detected = next(((media_type, suffix) for prefix, media_type, suffix in FILE_TYPES
                     if contents.startswith(prefix)), None)
    if detected is None:
        raise HTTPException(415, "PDF, PNG немесе JPEG файлын таңдаңыз.")
    media_type, suffix = detected
    original = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
    stem = "".join(char for char in original.rsplit(".", 1)[0] if char.isprintable())[:160].strip()
    safe_name = f"{stem or 'document'}{suffix}"
    lock_writes(db)
    item = parent_application(db, parent.id, app_id)
    require_editable(item)
    if document not in item.direction.document_slots:
        raise HTTPException(422, "Құжатты бағыттың тізімінен таңдаңыз.")
    record = db.scalar(select(Attachment).where(
        Attachment.application_id == app_id, Attachment.document == document,
    ))
    if record is None:
        count = db.scalar(select(func.count()).select_from(Attachment).where(Attachment.application_id == app_id))
        if count >= 12:
            raise HTTPException(409, "Өтінімге ең көбі 12 файл қосуға болады.")
        record = Attachment(application_id=app_id, document=document)
        db.add(record)
    record.filename = safe_name
    record.media_type = media_type
    record.size = len(contents)
    record.contents = contents
    db.commit()
    return record


@router.get("/{attachment_id}", response_class=Response)
def download(app_id: int, attachment_id: int, db: DB, user: Annotated[User, Depends(current_user)]):
    if user.role == "admin":
        submitted_application(db, app_id)
    else:
        parent_application(db, user.id, app_id)
    record = get_attachment(db, app_id, attachment_id)
    return Response(
        record.contents, media_type=record.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.filename, safe='')}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{attachment_id}", status_code=204)
def remove(app_id: int, attachment_id: int, db: DB, parent: Parent):
    lock_writes(db)
    item = parent_application(db, parent.id, app_id)
    require_editable(item)
    db.delete(get_attachment(db, app_id, attachment_id))
    db.commit()

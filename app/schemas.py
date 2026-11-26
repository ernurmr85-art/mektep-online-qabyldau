
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Language = Literal["kk", "ru"]
Grade = Annotated[int, Field(ge=1, le=11)]
Name = Annotated[str, Field(min_length=2, max_length=100)]
ReviewStatus = Literal["pending", "revision", "waitlisted", "accepted", "rejected"]
Status = Literal["draft"] | ReviewStatus
EventKind = Literal["created", "submitted", "resubmitted", "revision", "waitlisted", "accepted", "rejected"]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=8, max_length=72)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Literal["parent", "admin"]


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class DirectionCreate(Input):
    title: Name
    grade: Grade
    language: Language
    description: str = Field(min_length=10, max_length=1500)
    documents: str = Field(min_length=3, max_length=1500)
    opens_on: date
    closes_on: date
    active: bool = True
    capacity: int | None = Field(default=None, ge=0, le=10000)

    @model_validator(mode="after")
    def check_dates(self):
        if self.closes_on < self.opens_on:
            raise ValueError("Аяқталу күні басталу күнінен бұрын болмауы керек.")
        documents = [line.strip() for line in self.documents.splitlines() if line.strip()]
        if not 1 <= len(documents) <= 12 or len(set(documents)) != len(documents) or any(len(doc) > 160 for doc in documents):
            raise ValueError("Құжаттар тізімінде ұзындығы 160 таңбадан аспайтын 1–12 бірегей атау болуы керек.")
        return self


class DirectionRead(DirectionCreate):
    model_config = ConfigDict(from_attributes=True)

    # Existing records can contain document lists saved before slot validation.
    @model_validator(mode="after")
    def check_dates(self):
        return self

    id: int
    accepting: bool
    seats_remaining: int | None


class DirectionPage(BaseModel):
    items: list[DirectionRead]
    total: int
    page: int
    pages: int


class ApplicationFields(Input):
    student_name: Name
    iin: str = Field(pattern=r"^[0-9]{12}$", description="Оқушының 12 цифрлық ЖСН-і")
    parent_name: Name
    phone: str = Field(pattern=r"^\+?[0-9][0-9 ()-]{7,18}[0-9]$")
    address: str = Field(min_length=5, max_length=255)


class ApplicationCreate(ApplicationFields):
    direction_id: int = Field(gt=0)


class ApplicationRead(ApplicationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: DirectionRead
    status: Status
    decision_note: str | None
    created_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document: str
    filename: str
    media_type: str
    size: int


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: EventKind
    occurred_at: datetime
    note: str | None


class ApplicationDetail(ApplicationRead):
    attachments: list[AttachmentRead]
    events: list[EventRead]


class Decision(Input):
    status: Literal["accepted", "rejected", "revision"]
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def check_reason(self):
        if self.status in ("rejected", "revision") and not self.note:
            raise ValueError("Бас тарту немесе толықтыруға қайтару себебін көрсетіңіз.")
        return self

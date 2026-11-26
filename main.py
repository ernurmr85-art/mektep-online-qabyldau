
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.demo import setup_demo
from app.routers import accounts, applications, attachments, catalog, pages
from app.setup import initialize_database
from database import DEMO_MODE, ROOT


@asynccontextmanager
async def lifespan(_app):
    initialize_database()
    if DEMO_MODE:
        setup_demo()
    yield


app = FastAPI(
    title="Мектепке оқушыларды онлайн қабылдау жүйесі",
    description="Қабылдау бағыттарының каталогы, ата-ана кабинеті және қабылдау комиссиясы.",
    version="3.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
for router in (accounts.router, catalog.router, applications.router, attachments.router, pages.router):
    app.include_router(router)

if DEMO_MODE:
    app.include_router(accounts.demo_router)

    @app.middleware("http")
    async def local_demo_only(request: Request, call_next):
        if (not request.client or request.client.host not in {"127.0.0.1", "::1"}
                or request.url.hostname not in {"127.0.0.1", "localhost", "::1"}):
            return JSONResponse({"detail": "Демо нұсқа тек осы компьютерде қолжетімді."}, status_code=403)
        return await call_next(request)


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, error: HTTPException):
    if request.url.path.startswith(("/api", "/static")):
        return await http_exception_handler(request, error)
    message = "Сұралған бет табылмады." if error.detail == "Not Found" else error.detail
    response = pages.render(request, "error.html", None, code=error.status_code, message=message)
    response.status_code = error.status_code
    return response


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, error: RequestValidationError):
    if request.url.path.startswith("/api"):
        response = await request_validation_exception_handler(request, error)
        # Validation errors may refer to credentials or a child's personal data.
        import json

        details = json.loads(response.body)["detail"]
        for detail in details:
            detail.pop("input", None)
            detail.pop("ctx", None)
        return JSONResponse({"detail": details}, status_code=422)
    response = pages.render(request, "error.html", None, code=422, message="Сұраныс параметрлерін тексеріңіз.")
    response.status_code = 422
    return response
